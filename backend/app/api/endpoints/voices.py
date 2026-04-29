"""Voice profile endpoints (cloned voices)."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.db.models import VoiceProfile
from app.schemas.voices import (
    MAX_REFERENCE_TEXT_LEN,
    BuiltinVoice,
    SimilarityTestResponse,
    VoiceListResponse,
    VoiceProfileResponse,
    VoiceProfileUpdate,
    _normalise_reference_text,
)
from app.tasks.tts_tasks import clone_voice

router = APIRouter(prefix="/voices", tags=["voices"])

# Models that run on dedicated worker queues instead of the default "tts" queue
QUEUE_MAP: dict[str, str] = {
    "fish-speech-s2": "tts.fish-speech",
    "qwen3-tts": "tts.qwen3",
    "orpheus-3b": "tts.orpheus",
    "f5-tts": "tts.f5-tts",
    "chatterbox": "tts.f5-tts",
    "cosyvoice-2": "tts.f5-tts",
    "xtts-v2": "tts.xtts",
    "dia-1b": "tts.dia",
    "bark": "tts.bark",
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
    reference_text: str = Form(""),
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """Upload reference audio and create a voice profile.

    The voice embedding is generated asynchronously via a Celery task. The
    reference transcript is auto-detected by faster-whisper unless the caller
    supplied ``reference_text`` (a power-user override that skips ASR).
    """
    # Normalise / validate the optional manual transcript first so we fail
    # fast before touching disk. The schema-level cap is enforced via
    # ``_normalise_reference_text`` semantics.
    if reference_text and len(reference_text) > MAX_REFERENCE_TEXT_LEN:
        raise HTTPException(
            status_code=422,
            detail=(
                f"reference_text too long ({len(reference_text)} chars; "
                f"max {MAX_REFERENCE_TEXT_LEN})"
            ),
        )
    try:
        normalised_reference_text = _normalise_reference_text(reference_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Validate file type — accept all common audio containers (ffmpeg handles decoding)
    ALLOWED_TYPES = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/flac",
        "audio/x-flac",
        "audio/ogg",
        "audio/opus",
        "audio/mp4",
        "audio/x-m4a",
        "audio/aac",
        "video/mp4",  # browsers sometimes report M4A as video/mp4
    }
    content_type = (reference_audio.content_type or "").split(";")[0].strip()
    if content_type and content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported audio type: {content_type}. Use WAV, MP3, FLAC, M4A, or OGG.",
        )

    # Save reference audio
    voice_id = uuid.uuid4()
    audio_dir = Path(settings.AUDIO_OUTPUT_DIR) / "voices"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Whitelist extensions. The filename is user-controlled — taking only the
    # suffix via Path() and checking it against a known list means we can't
    # accidentally write an .exe or hit a case-difference issue in downstream
    # tools. The stored filename uses a generated UUID so the original basename
    # never reaches disk.
    ALLOWED_EXTS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".mp4", ".webm"}
    ext = Path(reference_audio.filename or "ref.wav").suffix.lower()
    if not ext or ext not in ALLOWED_EXTS:
        ext = ".wav"
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

    # Create DB record. If the user supplied a transcript, persist it as
    # ``manual`` (and skip ASR entirely); otherwise mark it ``pending`` and
    # dispatch the auto-transcribe task below.
    if normalised_reference_text:
        ref_text_value: str | None = normalised_reference_text
        ref_text_status = "manual"
    else:
        ref_text_value = None
        ref_text_status = "pending"

    profile = VoiceProfile(
        id=voice_id,
        name=name,
        model_id=model_id,
        reference_audio_path=str(ref_path),
        reference_text=ref_text_value,
        reference_text_status=ref_text_status,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # Dispatch embedding generation task (model-specific queue routing).
    queue = QUEUE_MAP.get(model_id, "tts")
    clone_voice.apply_async(args=[str(profile.id)], queue=queue)

    # Dispatch auto-transcription unless the user pre-filled the transcript.
    # Sending args by name to keep the call site readable; the task lives in
    # a separate worker container so we route via apply_async + queue.
    if ref_text_status == "pending" and settings.AUTO_TRANSCRIBE_REFERENCES:
        from app.tasks.asr_tasks import transcribe_reference

        transcribe_reference.apply_async(args=[str(profile.id)], queue="tts.asr")

    return VoiceProfileResponse.model_validate(profile)


# NOTE: /builtin/{model_id} must come BEFORE /{voice_id} to avoid route conflicts
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


@router.get("/{voice_id}", response_model=VoiceProfileResponse)
def get_voice_profile(voice_id: uuid.UUID, db: Session = Depends(get_db)) -> VoiceProfileResponse:
    """Get a single voice profile by ID."""
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return VoiceProfileResponse.model_validate(profile)


@router.patch("/{voice_id}", response_model=VoiceProfileResponse)
def update_voice_profile(
    voice_id: uuid.UUID,
    update: VoiceProfileUpdate,
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """Update name, description, tags, or reference transcript on a voice profile.

    Editing ``reference_text`` to a non-empty value flips the workflow status
    to ``"manual"`` so a late-running ASR task can never overwrite the user's
    edit. Clearing it (passing an empty string / ``None``) resets the status
    to ``"pending"`` and re-dispatches the auto-transcribe task.
    """
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    if update.name is not None:
        profile.name = update.name
    if update.description is not None:
        profile.description = update.description
    if update.tags is not None:
        profile.tags = update.tags

    # Track whether we need to (re-)dispatch ASR after the commit.
    redispatch_asr = False
    fields_set = update.model_fields_set
    if "reference_text" in fields_set:
        # ``_normalise_reference_text`` already turned empty/whitespace input
        # into ``None`` during validation.
        if update.reference_text is None:
            profile.reference_text = None
            profile.reference_text_status = "pending"
            redispatch_asr = True
        else:
            profile.reference_text = update.reference_text
            profile.reference_text_status = "manual"
    if "reference_language" in fields_set and update.reference_language is not None:
        profile.reference_language = update.reference_language

    db.commit()
    db.refresh(profile)

    if redispatch_asr and settings.AUTO_TRANSCRIBE_REFERENCES:
        from app.tasks.asr_tasks import transcribe_reference

        transcribe_reference.apply_async(args=[str(profile.id)], queue="tts.asr")

    return VoiceProfileResponse.model_validate(profile)


@router.post("/{voice_id}/transcribe", response_model=VoiceProfileResponse)
def retranscribe_voice_profile(
    voice_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """Re-run the auto-transcribe task for a voice profile.

    Resets ``reference_text`` to ``None`` and ``reference_text_status`` to
    ``"pending"`` before dispatching. Useful when the audio file changed or
    the previous attempt failed.
    """
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    profile.reference_text = None
    profile.reference_text_status = "pending"
    db.commit()
    db.refresh(profile)

    from app.tasks.asr_tasks import transcribe_reference

    transcribe_reference.apply_async(args=[str(profile.id)], queue="tts.asr")
    return VoiceProfileResponse.model_validate(profile)


@router.post("/{voice_id}/test", response_model=SimilarityTestResponse)
async def test_voice_similarity(
    voice_id: uuid.UUID,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SimilarityTestResponse:
    """Compute speaker similarity between the profile's reference and an upload.

    Convenience endpoint for debugging without going through the full TTS
    flow. Delegates to ``app.eval.similarity.reference_similarity`` which is
    expected to live in the ``worker-kokoro`` container (Phase 5). If
    speechbrain isn't yet deployed the endpoint will surface a 503.
    """
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    # Persist the uploaded clip to a temp file so the eval routine can open
    # it via path (consistent with how it reads the cached reference).
    suffix = Path(audio.filename or "test.wav").suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(prefix="voice_test_", suffix=suffix, delete=False) as tf:
        shutil.copyfileobj(audio.file, tf)
        tmp_path = Path(tf.name)

    try:
        try:
            from app.eval.similarity import reference_similarity
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail="Speaker-similarity backend not available",
            ) from exc

        similarity = float(reference_similarity(profile.reference_audio_path, str(tmp_path)))
    finally:
        tmp_path.unlink(missing_ok=True)

    return SimilarityTestResponse(similarity=similarity)


@router.get("/{voice_id}/audio")
def get_voice_audio(voice_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    """Return the reference audio file for a voice profile."""
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    ref_path = Path(profile.reference_audio_path)
    if not ref_path.exists():
        raise HTTPException(status_code=404, detail="Reference audio file not found on disk")

    ext = ref_path.suffix.lower()
    media_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
    }
    media_type = media_types.get(ext, "audio/wav")

    return FileResponse(
        path=str(ref_path),
        media_type=media_type,
        filename=f"voice_{voice_id}{ext}",
    )


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
