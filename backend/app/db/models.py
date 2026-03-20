"""SQLAlchemy ORM models for OpenSpeakers."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class TTSJob(Base):
    """A single TTS generation request."""

    __tablename__ = "tts_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    voice_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_profiles.id"), nullable=True
    )
    # Voice ID string (built-in voice slug or None)
    voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    voice_profile: Mapped["VoiceProfile | None"] = relationship(
        "VoiceProfile", back_populates="jobs", lazy="select"
    )


class VoiceProfile(Base):
    """A saved cloned voice that can be reused across TTS jobs."""

    __tablename__ = "voice_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reference_audio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Model-specific metadata (embedding file paths, etc.)
    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs: Mapped[list[TTSJob]] = relationship(
        "TTSJob", back_populates="voice_profile", lazy="select"
    )
