"""SQLAlchemy ORM models for OpenSpeakers."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TTSJob(Base):
    """A single TTS generation request."""

    __tablename__ = "tts_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    voice_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_profiles.id"), nullable=True
    )
    # Voice ID string (built-in voice slug or None)
    voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="jobstatus",
            create_constraint=True,
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cosine similarity in [-1, 1] between the cloned voice's reference audio
    # and the generated output. Populated asynchronously after generation by
    # the eval task; NULL for non-cloning jobs and legacy rows.
    speaker_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    voice_profile: Mapped[VoiceProfile | None] = relationship(
        "VoiceProfile", back_populates="jobs", lazy="select"
    )


class VoiceProfile(Base):
    """A saved cloned voice that can be reused across TTS jobs."""

    __tablename__ = "voice_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reference_audio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Model-specific extra info (embedding file paths, etc.)
    extra_info: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False, server_default="[]")
    # Reference transcript pipeline: ``reference_text`` is auto-populated by
    # faster-whisper on upload (or supplied by the user as a manual override).
    # ``reference_text_status`` surfaces ASR state to the UI:
    # ``pending`` (queued/running), ``ready`` (auto-detected), ``failed``
    # (ASR errored — UI prompts manual entry), ``manual`` (user typed/edited).
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_text_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    reference_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs: Mapped[list[TTSJob]] = relationship(
        "TTSJob", back_populates="voice_profile", lazy="select"
    )
