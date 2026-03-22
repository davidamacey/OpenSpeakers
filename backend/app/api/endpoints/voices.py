"""Voice profile endpoints (cloned voices)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.db.models import VoiceProfile
from app.schemas.voices import BuiltinVoice, VoiceListResponse, VoiceProfileResponse
from app.tasks.tts_tasks import clone_voice

router = APIRouter(prefix="/voices", tags=["voices"])

# Models that run on dedicated worker queues instead of the default "tts" queue
QUEUE_MAP: dict[str, str] = {
    "fish-speech-s2": "tts.fish-speech",
    "qwen3-tts": "tts.qwen3",
}

# Max reference audio duration in seconds (enforced upstream by the task)
MAX_REFERENCE_AUDIO_MB = 50


@router.get("", response_model=VoiceListResponse)
def list_voices(
    model_id: str | None = None,
    db: Session = Depends(get_db),
) -> VoiceListResponse:
    """List all saved voice profiles."""
    q = db.query(VoiceProfile)
    if model_id:
        q = q.filter(VoiceProfile.model_id == model_id)
    profiles = q.order_by(VoiceProfile.created_at.desc()).all()
    return VoiceListResponse(
        voices=[VoiceProfileResponse.model_validate(p) for p in profiles],
        total=len(profiles),
    )


@router.post("", response_model=VoiceProfileResponse, status_code=201)
async def create_voice_profile(
    name: str = Form(...),
    model_id: str = Form(...),
    reference_audio: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """Upload reference audio and create a voice profile.

    The voice embedding is generated asynchronously via a Celery task.
    """
    # Validate file type
    if reference_audio.content_type not in (
        "audio/wav",
        "audio/mpeg",
        "audio/flac",
        "audio/x-flac",
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported audio type: {reference_audio.content_type}. Use WAV, MP3, or FLAC.",
        )

    # Save reference audio
    voice_id = uuid.uuid4()
    audio_dir = Path(settings.AUDIO_OUTPUT_DIR) / "voices"
    audio_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(reference_audio.filename or "ref.wav").suffix or ".wav"
    ref_path = audio_dir / f"{voice_id}{ext}"

    with ref_path.open("wb") as f:
        shutil.copyfileobj(reference_audio.file, f)

    # Check file size
    size_mb = ref_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_REFERENCE_AUDIO_MB:
        ref_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large: {size_mb:.1f} MB > {MAX_REFERENCE_AUDIO_MB} MB",
        )

    # Create DB record
    profile = VoiceProfile(
        id=voice_id,
        name=name,
        model_id=model_id,
        reference_audio_path=str(ref_path),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # Dispatch embedding generation task (model-specific queue routing)
    queue = QUEUE_MAP.get(model_id, "tts")
    clone_voice.apply_async(args=[str(profile.id)], queue=queue)

    return VoiceProfileResponse.model_validate(profile)


@router.delete("/{voice_id}", status_code=204)
def delete_voice_profile(voice_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Delete a voice profile and its associated files."""
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    # Delete files
    for path_attr in ("reference_audio_path", "embedding_path"):
        path_str = getattr(profile, path_attr, None)
        if path_str:
            Path(path_str).unlink(missing_ok=True)

    db.delete(profile)
    db.commit()


@router.get("/builtin/{model_id}", response_model=list[BuiltinVoice])
def list_builtin_voices(model_id: str) -> list[BuiltinVoice]:
    """List built-in voices for a specific model."""
    from app.models.manager import ModelManager

    manager = ModelManager.get_instance()
    if model_id not in manager.registered_ids:
        raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")

    builtin: list[BuiltinVoice] = []

    if model_id == "vibevoice":
        from app.models.vibevoice import BUILTIN_VOICES

        for voice_id, slug in BUILTIN_VOICES.items():
            parts = voice_id.split("-")
            lang = parts[0] if parts else "en"
            gender = "female" if "woman" in slug else "male"
            builtin.append(
                BuiltinVoice(
                    id=voice_id,
                    name=voice_id,
                    language=lang,
                    gender=gender,
                    model_id=model_id,
                )
            )

    elif model_id == "kokoro":
        from app.models.kokoro import KOKORO_VOICES

        for voice_id in KOKORO_VOICES:
            parts = voice_id.split("-")
            lang = parts[0] if parts else "en"
            gender = parts[1] if len(parts) > 1 else None
            builtin.append(
                BuiltinVoice(
                    id=voice_id,
                    name=voice_id,
                    language=lang,
                    gender=gender,
                    model_id=model_id,
                )
            )

    return builtin
