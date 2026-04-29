"""Celery tasks for objective evaluation metrics (Phase 5).

Currently provides ``compute_similarity`` — runs ECAPA-TDNN on the reference and
generated audio for a completed cloned-voice TTS job and writes the cosine
similarity (a float in [-1, 1]) to ``TTSJob.speaker_similarity``.

The task is best-effort: any failure (model download, decode error, missing
files) is logged and the column is left ``None``. It must NEVER block or fail
the originating TTS job.

Runs on the ``tts.kokoro`` queue — the always-on worker-kokoro container is the
designated home for the speechbrain dependency, so we piggyback there to avoid a
separate eval worker.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.core.celery import celery_app
from app.core.config import settings
from app.db.models import TTSJob, VoiceProfile

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    """Create a standalone DB session (matches tts_tasks.py pattern)."""
    from app.core.database import SessionLocal

    return SessionLocal()


def _resolve_reference_path(profile: VoiceProfile) -> str:
    """Return the path to the cleaned reference audio when available, else raw.

    Phase 2 introduces a ``prepare_reference_to_file`` helper that returns a
    cached, cleaned WAV. We try to use it so the embedding is computed on the
    same audio the model heard. If the helper isn't available yet (parallel
    Phase 2 work) we fall back to the raw upload path.
    """
    raw_path = profile.reference_audio_path
    try:
        from app.models._ref_audio import prepare_reference_to_file  # type: ignore

        cleaned = prepare_reference_to_file(raw_path, target_sr=16000, max_seconds=30)
        if cleaned and Path(cleaned).exists():
            return str(cleaned)
    except Exception:
        # Helper missing or raised — best-effort, fall back to raw path.
        logger.debug("prepare_reference_to_file unavailable; using raw reference audio")
    return raw_path


def _embedding_cache_path(profile_id: uuid.UUID) -> Path:
    return Path(settings.AUDIO_OUTPUT_DIR) / "voices" / "_embed" / f"{profile_id}.npy"


def _load_or_compute_reference_embedding(
    db: Session, profile: VoiceProfile, ref_audio_path: str
) -> np.ndarray:
    """Return the reference embedding, caching it on ``VoiceProfile.embedding_path``."""
    from app.eval.similarity import speaker_embedding

    cached_path = profile.embedding_path
    if cached_path:
        try:
            cached = Path(cached_path)
            if cached.exists() and cached.suffix == ".npy":
                arr = np.load(cached).astype(np.float32, copy=False)
                if arr.ndim == 1 and arr.size > 0:
                    return arr
        except Exception:
            logger.warning("failed to load cached reference embedding %s; recomputing", cached_path)

    emb = speaker_embedding(ref_audio_path)

    target = _embedding_cache_path(profile.id)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        np.save(target, emb)
        # Only overwrite embedding_path if the existing one isn't already a model-specific
        # voice clone artefact (e.g. .pt / .pth from clone_voice). We treat .npy as ours.
        existing = profile.embedding_path or ""
        if not existing or existing.endswith(".npy"):
            profile.embedding_path = str(target)
            db.commit()
    except Exception:
        logger.warning("failed to persist reference embedding cache at %s", target, exc_info=True)
    return emb


@celery_app.task(
    name="eval.compute_similarity",
    queue="tts.kokoro",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def compute_similarity(job_id: str) -> None:
    """Compute and persist speaker similarity for a completed cloned-voice job.

    Best-effort: catches all exceptions, logs them, and leaves
    ``TTSJob.speaker_similarity = None`` rather than failing the task.
    """
    db = _get_db()
    try:
        try:
            job_uuid = uuid.UUID(job_id)
        except (TypeError, ValueError):
            logger.warning("compute_similarity: invalid job_id %r", job_id)
            return

        job = db.query(TTSJob).filter(TTSJob.id == job_uuid).first()
        if job is None:
            logger.info("compute_similarity: job %s not found (deleted?)", job_id)
            return

        if job.voice_profile_id is None:
            logger.debug("compute_similarity: job %s has no voice_profile_id; skipping", job_id)
            return

        gen_path = job.output_path
        if not gen_path or not Path(gen_path).exists():
            logger.info(
                "compute_similarity: job %s has no audio_path on disk (%r); skipping",
                job_id,
                gen_path,
            )
            return

        profile = db.query(VoiceProfile).filter(VoiceProfile.id == job.voice_profile_id).first()
        if profile is None:
            logger.info(
                "compute_similarity: voice profile %s missing for job %s",
                job.voice_profile_id,
                job_id,
            )
            return

        if not profile.reference_audio_path or not Path(profile.reference_audio_path).exists():
            logger.info(
                "compute_similarity: reference audio missing for profile %s (path=%r)",
                profile.id,
                profile.reference_audio_path,
            )
            return

        ref_path = _resolve_reference_path(profile)

        try:
            ref_emb = _load_or_compute_reference_embedding(db, profile, ref_path)
        except Exception:
            logger.warning(
                "compute_similarity: reference embedding failed for profile %s",
                profile.id,
                exc_info=True,
            )
            job.speaker_similarity = None
            db.commit()
            return

        try:
            from app.eval.similarity import cosine_similarity, speaker_embedding

            gen_emb = speaker_embedding(gen_path)
            score = cosine_similarity(ref_emb, gen_emb)
        except Exception:
            logger.warning(
                "compute_similarity: generated-audio embedding failed for job %s",
                job_id,
                exc_info=True,
            )
            job.speaker_similarity = None
            db.commit()
            return

        job.speaker_similarity = float(score)
        db.commit()
        logger.info("compute_similarity: job %s score=%.3f", job_id, score)
    except Exception:
        # Outermost guard — never let this task explode and retry forever.
        logger.exception("compute_similarity: unexpected failure for job %s", job_id)
    finally:
        db.close()
