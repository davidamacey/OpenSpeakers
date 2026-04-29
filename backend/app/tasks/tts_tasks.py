"""Celery tasks for TTS generation and voice cloning.

All GPU inference happens here — never in the FastAPI process.
The Celery worker runs with --concurrency=1 to prevent GPU memory contention.

Progress is published to Redis pub/sub (see app.api.websockets) so the
FastAPI WebSocket endpoint can stream it to the browser in real time.
"""

from __future__ import annotations

import base64
import io
import logging
import time
import uuid
import wave
from datetime import UTC, datetime
from pathlib import Path

from celery import Task

from app.api.websockets import publish_progress_sync
from app.core.celery import celery_app
from app.core.config import settings
from app.db.models import JobStatus, TTSJob, VoiceProfile
from app.models.base import GenerateRequest

logger = logging.getLogger(__name__)


def _get_db():
    """Create a standalone DB session (not a FastAPI dependency)."""
    from app.core.database import SessionLocal

    return SessionLocal()


def _wait_for_transcript(profile: VoiceProfile, db, timeout_s: float = 5.0) -> None:
    """Briefly poll the DB for ASR completion before generation kicks off.

    The auto-transcribe pipeline normally finishes well before the user
    submits a TTS job, but a short clip uploaded immediately followed by a
    generate request can race the ASR task. We refresh the existing
    ``profile`` row every 250 ms up to ``timeout_s`` and return silently on
    timeout — downstream models still have their no-transcript fallback
    paths. Using ``db.refresh`` avoids issuing a fresh SELECT each tick.
    """
    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        if profile.reference_text_status != "pending":
            return
        time.sleep(0.25)
        try:
            db.refresh(profile)
        except Exception:
            # Row deleted out from under us, or session error — give up
            # quietly; downstream models have a no-transcript fallback.
            return


def _pub(job_id: str, event: dict) -> None:
    """Fire-and-forget progress publish — never crashes the task on failure."""
    try:
        publish_progress_sync(job_id, event)
    except Exception:
        logger.debug("Progress publish failed for job %s (non-fatal)", job_id)


class TTSTask(Task):
    """Base task class that lazily initialises the ModelManager once per worker process."""

    _manager = None

    @property
    def manager(self):
        if self._manager is None:
            from app.models.manager import ModelManager

            self._manager = ModelManager.get_instance()
        return self._manager


@celery_app.task(
    bind=True,
    base=TTSTask,
    name="app.tasks.tts_tasks.generate_tts",
    queue="tts",
    max_retries=0,
    track_started=True,
    soft_time_limit=600,  # 10 min soft limit
    time_limit=660,  # 11 min hard limit
)
def generate_tts(self: TTSTask, job_id: str) -> dict:
    """Generate TTS audio for the given job.

    Publishes WebSocket-compatible progress events to Redis throughout execution.
    """
    db = _get_db()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == uuid.UUID(job_id)).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Check if already cancelled (race condition: user cancelled while queued)
        if job.status == JobStatus.CANCELLED:
            return {"job_id": job_id, "status": "cancelled"}

        job.status = JobStatus.RUNNING
        db.commit()

        # Store celery task ID so it can be revoked for cancellation
        job.celery_task_id = self.request.id
        db.commit()

        _pub(
            job_id,
            {
                "type": "status",
                "status": "running",
                "detail": "Job picked up by worker…",
            },
        )

        t_start = time.monotonic()

        # ── Step 1: Resolve voice ─────────────────────────────────────────────
        # Each model expects ``request.voice_id`` to be either a built-in slug
        # (e.g. Kokoro's ``af_bella``) or a path to a reference clip on disk.
        # When the user submits a job with a VoiceProfile UUID, the API stores
        # that UUID in both ``job.voice_id`` *and* ``job.voice_profile_id`` —
        # we must rewrite ``voice_id`` to the actual audio path here, otherwise
        # the model sees a UUID string, ``Path(voice_id).exists()`` returns
        # False, and cloning silently falls back to the model's default voice.
        voice_id = job.voice_id
        profile: VoiceProfile | None = None
        if job.voice_profile_id:
            profile = db.query(VoiceProfile).filter(VoiceProfile.id == job.voice_profile_id).first()
            if profile:
                # ``embedding_path`` is overloaded: clone-capable models that
                # actually need a learned embedding (Chatterbox .pt, Dia .pt)
                # store the artefact there, but the eval pipeline *also* caches
                # its ECAPA reference embedding to ``{id}.npy`` and writes the
                # path back to the same column. A ``.npy`` is NOT a voice-clone
                # asset for any TTS model — passing it as ``voice_id`` makes
                # zero-shot models (Fish, F5, CosyVoice, VibeVoice) try to
                # decode it as audio and fail. Fall back to the raw reference
                # audio in that case.
                voice_artifact = profile.embedding_path or ""
                if voice_artifact.endswith(".npy"):
                    voice_artifact = ""
                voice_id = voice_artifact or profile.reference_audio_path

        params = job.parameters or {}
        extra = dict(params.get("extra") or {})

        # Inject the reference transcript so cloning models can pick it up via
        # ``request.extra["ref_text"]``. If ASR is still in flight we wait
        # briefly (5 s cap) for it to land, then refresh the profile. A
        # caller-supplied ``ref_text`` always wins.
        if profile and profile.reference_text_status == "pending":
            _wait_for_transcript(profile, db, timeout_s=5.0)
        if profile and profile.reference_text and "ref_text" not in extra:
            extra["ref_text"] = profile.reference_text

        request = GenerateRequest(
            text=job.text,
            voice_id=voice_id,
            speed=params.get("speed", 1.0),
            pitch=params.get("pitch", 0.0),
            language=params.get("language", "en"),
            extra=extra,
        )

        # ── Step 2: Load model ────────────────────────────────────────────────
        _pub(
            job_id,
            {
                "type": "progress",
                "step": "model_loading",
                "percent": 0,
                "detail": f"Loading {job.model_id}…",
            },
        )

        model = self.manager.load_model(job.model_id)

        _pub(
            job_id,
            {
                "type": "progress",
                "step": "model_loading",
                "percent": 100,
                "detail": f"{job.model_id} loaded, starting synthesis…",
            },
        )

        # ── Step 3: Generate audio (streaming or batch) ──────────────────────
        _pub(
            job_id,
            {
                "type": "progress",
                "step": "generating",
                "percent": 0,
                "detail": f"Generating {len(job.text)} characters…",
            },
        )

        self.manager.mark_in_use()
        try:
            if getattr(model, "supports_streaming", False):
                # Streaming: publish PCM16 chunks to Redis as they arrive,
                # then assemble a final WAV from all chunks.
                all_pcm_chunks: list[bytes] = []
                stream_sample_rate = 24000

                for chunk_index, pcm16_bytes in enumerate(model.stream_generate(request)):
                    all_pcm_chunks.append(pcm16_bytes)
                    _pub(
                        job_id,
                        {
                            "type": "audio_chunk",
                            "chunk_data": base64.b64encode(pcm16_bytes).decode("ascii"),
                            "chunk_index": chunk_index,
                            "sample_rate": stream_sample_rate,
                        },
                    )

                # Assemble final WAV from all collected PCM16 chunks
                all_pcm = b"".join(all_pcm_chunks)
                num_samples = len(all_pcm) // 2  # PCM16 = 2 bytes per sample
                duration_seconds = num_samples / stream_sample_rate

                wav_buf = io.BytesIO()
                with wave.open(wav_buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(stream_sample_rate)
                    wf.writeframes(all_pcm)
                wav_buf.seek(0)
                audio_bytes = wav_buf.read()
                audio_format = "wav"
            else:
                result = model.generate(request)
                audio_bytes = result.audio_bytes
                duration_seconds = result.duration_seconds
                audio_format = result.format
        finally:
            self.manager.mark_done()

        _pub(
            job_id,
            {
                "type": "progress",
                "step": "generating",
                "percent": 100,
                "detail": "Saving audio…",
            },
        )

        # ── Step 4: Save audio ────────────────────────────────────────────────
        output_dir = Path(settings.AUDIO_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_id}.{audio_format}"
        output_path.write_bytes(audio_bytes)

        # Transcode to requested output format if different from generated format
        output_format = params.get("output_format", "wav")
        if output_format != "wav" and output_format != audio_format:
            import subprocess

            codec_map = {"mp3": "libmp3lame", "ogg": "libvorbis"}
            codec = codec_map.get(output_format)
            if codec:
                target_path = output_dir / f"{job_id}.{output_format}"
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(output_path),
                        "-codec:a",
                        codec,
                        str(target_path),
                    ],
                    capture_output=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    output_path.unlink(missing_ok=True)
                    output_path = target_path
                    audio_format = output_format

        processing_time_ms = int((time.monotonic() - t_start) * 1000)

        # ── Step 5: Update DB ─────────────────────────────────────────────────
        job.status = JobStatus.COMPLETE
        job.output_path = str(output_path)
        job.duration_seconds = duration_seconds
        job.processing_time_ms = processing_time_ms
        job.completed_at = datetime.now(UTC)
        db.commit()

        # Apply keep_alive TTL so unload_all() in finally respects it
        keep_alive = params.get("keep_alive")
        if keep_alive is not None:
            self.manager.set_keep_alive(job.model_id, keep_alive)

        # Trigger speaker-similarity scoring for cloned-voice jobs. Routed to
        # the always-on ``tts.kokoro`` queue (worker-kokoro carries the
        # speechbrain ECAPA model per Phase 5). Failures here must never
        # surface to the user — the TTS job already succeeded.
        if job.status == JobStatus.COMPLETE and job.voice_profile_id and job.output_path:
            try:
                from app.tasks.eval_tasks import compute_similarity

                compute_similarity.apply_async(
                    args=[str(job.id)],
                    queue="tts.kokoro",
                )
            except ImportError:
                # eval_tasks not yet deployed (Phase 5) — silently skip.
                logger.debug("eval_tasks not available; skipping similarity scoring")
            except Exception:
                logger.exception("Failed to dispatch similarity task for job %s", job_id)

        _pub(
            job_id,
            {
                "type": "complete",
                "job_id": job_id,
                "audio_url": f"/api/tts/jobs/{job_id}/audio",
                "duration": duration_seconds,
                "processing_ms": processing_time_ms,
            },
        )

        logger.info(
            "Job %s complete: %.1fs audio in %dms (model=%s)",
            job_id,
            duration_seconds,
            processing_time_ms,
            job.model_id,
        )

        return {"job_id": job_id, "status": "complete", "output_path": str(output_path)}

    except Exception as exc:
        logger.exception("Job %s failed (model=%s)", job_id, getattr(job, "model_id", "?"))
        _pub(job_id, {"type": "error", "message": str(exc)})
        try:
            job = db.query(TTSJob).filter(TTSJob.id == uuid.UUID(job_id)).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                job.completed_at = datetime.now(UTC)
                db.commit()
        except Exception:
            logger.exception("Failed to update job status for %s", job_id)
        raise
    finally:
        # Always unload model to free GPU VRAM — on success AND failure.
        # Prevents broken model state from persisting after errors.
        try:
            self.manager.unload_all()
        except Exception:
            logger.debug("unload_all failed in finally (non-fatal)")
        db.close()


@celery_app.task(
    bind=True,
    base=TTSTask,
    name="app.tasks.tts_tasks.clone_voice",
    queue="tts",
    max_retries=0,
    track_started=True,
    soft_time_limit=300,
    time_limit=360,
)
def clone_voice(self: TTSTask, voice_profile_id: str) -> dict:
    """Generate speaker embedding for a VoiceProfile record.

    The reference audio must already be saved to disk before calling this task.
    """
    db = _get_db()
    try:
        profile = (
            db.query(VoiceProfile).filter(VoiceProfile.id == uuid.UUID(voice_profile_id)).first()
        )
        if not profile:
            raise ValueError(f"VoiceProfile {voice_profile_id} not found")

        logger.info("Cloning voice %r with model %s", profile.name, profile.model_id)
        model = self.manager.load_model(profile.model_id)

        if not model.supports_voice_cloning:
            raise ValueError(f"Model {profile.model_id} does not support voice cloning")

        self.manager.mark_in_use()
        try:
            metadata = model.clone_voice(
                audio_path=profile.reference_audio_path,
                name=profile.name,
            )
        finally:
            self.manager.mark_done()

        profile.extra_info = metadata
        if "embedding_path" in metadata:
            profile.embedding_path = metadata["embedding_path"]
        db.commit()

        logger.info("Voice cloning complete for profile %s", voice_profile_id)
        return {"voice_profile_id": voice_profile_id, "status": "complete"}
    except Exception:
        logger.exception("Voice cloning failed for %s", voice_profile_id)
        raise
    finally:
        try:
            self.manager.unload_all()
        except Exception:
            logger.debug("unload_all failed in clone_voice finally (non-fatal)")
        db.close()
