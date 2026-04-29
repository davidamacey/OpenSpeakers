"""Celery task that transcribes a voice profile's reference audio.

Runs on the dedicated ``tts.asr`` queue (``worker-asr`` container). The task
is idempotent and respects user edits: if the profile's
``reference_text_status`` has already been flipped to ``"manual"`` the task
returns without touching the row.
"""

from __future__ import annotations

import logging
import uuid

from app.core.celery import celery_app
from app.db.models import VoiceProfile

logger = logging.getLogger(__name__)


def _get_db():
    """Create a standalone DB session (not a FastAPI dependency)."""
    from app.core.database import SessionLocal

    return SessionLocal()


@celery_app.task(
    name="asr.transcribe_reference",
    queue="tts.asr",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    track_started=True,
    soft_time_limit=180,
    time_limit=240,
)
def transcribe_reference(voice_profile_id: str) -> dict:
    """Run faster-whisper against ``voice_profile_id``'s reference audio.

    Persists ``reference_text``, ``reference_language`` and flips
    ``reference_text_status`` to ``"ready"`` (or ``"failed"`` on error).
    User-edited rows (status == ``"manual"``) are skipped so a late-running
    ASR task can never clobber an explicit edit.
    """
    # Lazy import — the ASR module pulls in faster-whisper which is only
    # installed in the worker-asr container.
    from app.asr.whisper import transcribe

    db = _get_db()
    profile: VoiceProfile | None = None
    try:
        try:
            pid = uuid.UUID(voice_profile_id)
        except (TypeError, ValueError):
            logger.warning("transcribe_reference: invalid uuid %r", voice_profile_id)
            return {"voice_profile_id": voice_profile_id, "status": "invalid"}

        profile = db.query(VoiceProfile).filter(VoiceProfile.id == pid).first()
        if profile is None:
            logger.info("transcribe_reference: profile %s not found", voice_profile_id)
            return {"voice_profile_id": voice_profile_id, "status": "missing"}

        # User-edited transcripts win over auto-detection unconditionally.
        if profile.reference_text_status == "manual":
            logger.info(
                "transcribe_reference: profile %s already manual — skipping",
                voice_profile_id,
            )
            return {"voice_profile_id": voice_profile_id, "status": "manual"}

        try:
            text, language = transcribe(profile.reference_audio_path)
        except Exception:
            # Re-raise after marking the row failed so Celery's retry kicks
            # in (autoretry_for=Exception, max_retries=2).
            profile.reference_text_status = "failed"
            raise

        profile.reference_text = text
        profile.reference_language = language
        profile.reference_text_status = "ready"
        logger.info(
            "transcribe_reference: profile %s ready (lang=%s, %d chars)",
            voice_profile_id,
            language,
            len(text),
        )
        return {
            "voice_profile_id": voice_profile_id,
            "status": "ready",
            "language": language,
        }
    finally:
        try:
            db.commit()
        except Exception:
            logger.exception("transcribe_reference: commit failed for %s", voice_profile_id)
            db.rollback()
        db.close()
