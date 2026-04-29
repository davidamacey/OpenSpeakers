"""faster-whisper singleton wrapper for reference-audio transcription.

The model is lazy-loaded on first use and reused across calls so the Celery
worker only pays the cold-start cost once. Configuration comes from
:mod:`app.core.config` (``WHISPER_MODEL``, ``WHISPER_DEVICE``,
``WHISPER_COMPUTE_TYPE``).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover — typing only
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_MODEL: WhisperModel | None = None
_MODEL_LOCK = threading.Lock()


class WhisperTranscriptionError(RuntimeError):
    """Raised when faster-whisper produces no usable transcript."""


def _get_model() -> WhisperModel:
    """Return the lazily-initialised faster-whisper model singleton."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    with _MODEL_LOCK:
        if _MODEL is not None:  # pragma: no cover — double-checked locking
            return _MODEL

        # Imported lazily so the backend container (which doesn't ship
        # faster-whisper) can still import this module for type hints.
        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model=%s device=%s compute_type=%s",
            settings.WHISPER_MODEL,
            settings.WHISPER_DEVICE,
            settings.WHISPER_COMPUTE_TYPE,
        )
        _MODEL = WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )
    return _MODEL


def transcribe(audio_path: str | Path) -> tuple[str, str]:
    """Transcribe ``audio_path`` with faster-whisper.

    Returns ``(text, detected_language)`` — both strings. ``detected_language``
    is the ISO-639-1 code Whisper reports (e.g. ``"en"``, ``"es"``).

    Raises:
        FileNotFoundError: if ``audio_path`` does not exist on disk.
        WhisperTranscriptionError: if Whisper produces empty output (e.g. the
            VAD filter dropped every segment as silence).
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    model = _get_model()
    segments, info = model.transcribe(str(path), vad_filter=True, beam_size=5)
    # ``segments`` is a generator; iterate once to materialise.
    joined = "".join(seg.text for seg in segments).strip()
    if not joined:
        raise WhisperTranscriptionError(
            f"faster-whisper produced no text for {path} (silence or VAD-filtered)"
        )
    language = (info.language or "").strip() or "und"
    return joined, language
