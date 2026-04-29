"""Automatic speech recognition utilities.

The :mod:`app.asr.whisper` submodule wraps faster-whisper with a singleton
loader so reference-audio transcripts can be produced without paying the
model-load cost on every Celery task.
"""

from app.asr.whisper import transcribe

__all__ = ["transcribe"]
