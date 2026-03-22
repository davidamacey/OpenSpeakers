"""Initial schema — tts_jobs and voice_profiles tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("reference_audio_path", sa.String(512), nullable=False),
        sa.Column("embedding_path", sa.String(512), nullable=True),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voice_profiles_model_id", "voice_profiles", ["model_id"])

    op.create_table(
        "tts_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("voice_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("voice_id", sa.String(128), nullable=True),
        sa.Column("parameters", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "complete", "failed", name="jobstatus"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("output_path", sa.String(512), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tts_jobs_model_id", "tts_jobs", ["model_id"])
    op.create_index("ix_tts_jobs_status", "tts_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("tts_jobs")
    op.drop_table("voice_profiles")
    op.execute("DROP TYPE IF EXISTS jobstatus")
