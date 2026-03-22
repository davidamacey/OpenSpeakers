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
    extra: dict = Field(default_factory=dict, description="Model-specific parameters")


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

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int
