from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Status values for the reference-transcript pipeline.
ReferenceTextStatus = Literal["pending", "ready", "failed", "manual"]

# Maximum length of a reference transcript (auto-detected or manually entered).
# Anything beyond this is almost certainly the wrong field; the upstream
# upload handler enforces the same cap with a 422 response.
MAX_REFERENCE_TEXT_LEN = 4000


def _normalise_reference_text(value: str | None) -> str | None:
    """Strip surrounding whitespace, reject control chars (except \\n / \\t),
    and treat empty strings as ``None`` so downstream ``if profile.reference_text``
    checks remain uniform."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    for ch in cleaned:
        if ord(ch) < 0x20 and ch not in ("\n", "\t"):
            raise ValueError("reference_text contains disallowed control characters")
    return cleaned


class VoiceProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    model_id: str = Field(..., description="Which model this voice is for")
    reference_text: str | None = Field(default=None, max_length=MAX_REFERENCE_TEXT_LEN)

    @field_validator("reference_text", mode="before")
    @classmethod
    def _validate_reference_text(cls, v: str | None) -> str | None:
        return _normalise_reference_text(v)


class VoiceProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    model_id: str
    reference_audio_path: str
    embedding_path: str | None
    extra_info: dict | None
    description: str | None = None
    tags: list = Field(default_factory=list)
    reference_text: str | None = None
    reference_text_status: ReferenceTextStatus = "pending"
    reference_language: str | None = None
    created_at: datetime
    avg_similarity: float | None = Field(
        None,
        description=(
            "Mean speaker_similarity across all completed jobs that used this voice "
            "profile. NULL when no scored jobs exist yet."
        ),
    )
    similarity_count: int = Field(
        0,
        description=(
            "Number of completed jobs with a non-null speaker_similarity for this profile."
        ),
    )

    model_config = {"from_attributes": True}


class VoiceProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    tags: list[str] | None = None
    reference_text: str | None = Field(default=None, max_length=MAX_REFERENCE_TEXT_LEN)
    reference_language: str | None = Field(default=None, max_length=8)

    @field_validator("reference_text", mode="before")
    @classmethod
    def _validate_reference_text(cls, v: str | None) -> str | None:
        return _normalise_reference_text(v)


class VoiceListResponse(BaseModel):
    voices: list[VoiceProfileResponse]
    total: int


class BuiltinVoice(BaseModel):
    """A built-in (non-cloned) voice shipped with a model."""

    id: str
    name: str
    language: str
    gender: str | None = None
    model_id: str


class SimilarityTestResponse(BaseModel):
    """Response from POST /api/voices/{id}/test."""

    similarity: float
