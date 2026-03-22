"""Celery tasks for TTS generation and voice cloning.

All GPU inference happens here — never in the FastAPI process.
The Celery worker runs with --concurrency=1 to prevent GPU memory contention.

Progress is published to Redis pub/sub (see app.api.websockets) so the
FastAPI WebSocket endpoint can stream it to the browser in real time.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
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

        job.status = JobStatus.RUNNING
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
        voice_id = job.voice_id
        if job.voice_profile_id and not voice_id:
            profile = (
                db.query(VoiceProfile)
                .filter(VoiceProfile.id == job.voice_profile_id)
                .first()
            )
            if profile:
                voice_id = profile.embedding_path or profile.reference_audio_path

        params = job.parameters or {}
        request = GenerateRequest(
            text=job.text,
            voice_id=voice_id,
            speed=params.get("speed", 1.0),
            pitch=params.get("pitch", 0.0),
            language=params.get("language", "en"),
            extra=params.get("extra", {}),
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

        # ── Step 3: Generate audio ────────────────────────────────────────────
        _pub(
            job_id,
            {
                "type": "progress",
                "step": "generating",
                "percent": 0,
                "detail": f"Generating {len(job.text)} characters…",
            },
        )

        result = model.generate(request)

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
        output_path = output_dir / f"{job_id}.{result.format}"
        output_path.write_bytes(result.audio_bytes)

        processing_time_ms = int((time.monotonic() - t_start) * 1000)

        # ── Step 5: Update DB ─────────────────────────────────────────────────
        job.status = JobStatus.COMPLETE
        job.output_path = str(output_path)
        job.duration_seconds = result.duration_seconds
        job.processing_time_ms = processing_time_ms
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        _pub(
            job_id,
            {
                "type": "complete",
                "job_id": job_id,
                "audio_url": f"/api/tts/jobs/{job_id}/audio",
                "duration": result.duration_seconds,
                "processing_ms": processing_time_ms,
            },
        )

        logger.info(
            "Job %s complete: %.1fs audio in %dms (model=%s)",
            job_id,
            result.duration_seconds,
            processing_time_ms,
            job.model_id,
        )

        # Unload model to free GPU VRAM for other workers sharing the GPU
        self.manager.unload_all()

        return {"job_id": job_id, "status": "complete", "output_path": str(output_path)}

    except Exception as exc:
        logger.exception(
            "Job %s failed (model=%s)", job_id, getattr(job, "model_id", "?")
        )
        _pub(job_id, {"type": "error", "message": str(exc)})
        try:
            job = db.query(TTSJob).filter(TTSJob.id == uuid.UUID(job_id)).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            logger.exception("Failed to update job status for %s", job_id)
        raise
    finally:
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
            db.query(VoiceProfile)
            .filter(VoiceProfile.id == uuid.UUID(voice_profile_id))
            .first()
        )
        if not profile:
            raise ValueError(f"VoiceProfile {voice_profile_id} not found")

        logger.info("Cloning voice %r with model %s", profile.name, profile.model_id)
        model = self.manager.load_model(profile.model_id)

        if not model.supports_voice_cloning:
            raise ValueError(f"Model {profile.model_id} does not support voice cloning")

        metadata = model.clone_voice(
            audio_path=profile.reference_audio_path,
            name=profile.name,
        )

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
        db.close()
