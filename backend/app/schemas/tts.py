from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import JobStatus


class GenerateRequest(BaseModel):
    model_id: str = Field(..., description="Model to use for generation")
    text: str = Field(..., min_length=1, max_length=4096)
    voice_id: str | None = Field(None, description="Built-in voice slug or voice profile ID")
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-12.0, le=12.0)
    language: str = Field("en", description="BCP-47 language code")
    output_format: str = Field("wav", pattern="^(wav|mp3|ogg)$")
    extra: dict = Field(default_factory=dict, description="Model-specific parameters")
    keep_alive: int | None = Field(
        None,
        description=(
            "Seconds to keep model in GPU VRAM after generation. "
            "-1 = keep indefinitely, 0 = unload immediately, "
            "None = use server default (MODEL_IDLE_TIMEOUT env var)."
        ),
    )


class GenerateResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    message: str = "Job queued"


class JobResponse(BaseModel):
    id: uuid.UUID
    model_id: str
    text: str
    voice_id: str | None
    voice_profile_id: uuid.UUID | None
    parameters: dict | None
    status: JobStatus
    error_message: str | None
    output_path: str | None
    duration_seconds: float | None
    processing_time_ms: int | None
    created_at: datetime
    completed_at: datetime | None
    batch_id: uuid.UUID | None = None
    celery_task_id: str | None = None
    speaker_similarity: float | None = Field(
        None,
        description=(
            "Cosine speaker-similarity score in [-1, 1] between the generated "
            "audio and the voice profile's reference clip. NULL when no voice "
            "profile was used or the eval task hasn't run yet. >=0.5 typically "
            "indicates a same-speaker match."
        ),
    )

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int


class BatchGenerateRequest(BaseModel):
    lines: list[str] = Field(..., min_length=1, max_length=100)
    model_id: str
    voice_id: str | None = None
    language: str = "en"
    speed: float = Field(1.0, ge=0.5, le=2.0)
    output_format: str = Field("wav", pattern="^(wav|mp3|ogg)$")
    extra: dict = Field(default_factory=dict)


class BatchGenerateResponse(BaseModel):
    batch_id: uuid.UUID
    job_ids: list[uuid.UUID]
    total: int


class BatchStatusResponse(BaseModel):
    batch_id: uuid.UUID
    total: int
    status_counts: dict[str, int]
    jobs: list[JobResponse]
