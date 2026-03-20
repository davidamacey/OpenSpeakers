"""Structured exception types for OpenSpeakers."""
from __future__ import annotations

from fastapi import HTTPException


class OpenSpeakersError(Exception):
    """Base error."""


class ModelNotFoundError(OpenSpeakersError):
    def __init__(self, model_id: str) -> None:
        super().__init__(f"Model {model_id!r} is not registered")
        self.model_id = model_id


class ModelLoadError(OpenSpeakersError):
    def __init__(self, model_id: str, cause: str) -> None:
        super().__init__(f"Failed to load model {model_id!r}: {cause}")
        self.model_id = model_id


class GenerationError(OpenSpeakersError):
    def __init__(self, model_id: str, cause: str) -> None:
        super().__init__(f"Generation failed with {model_id!r}: {cause}")
        self.model_id = model_id


class JobNotFoundError(OpenSpeakersError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id!r} not found")
        self.job_id = job_id


class VoiceProfileNotFoundError(OpenSpeakersError):
    def __init__(self, voice_id: str) -> None:
        super().__init__(f"Voice profile {voice_id!r} not found")
        self.voice_id = voice_id
