"""Add speaker_similarity column to tts_jobs.

Revision ID: 004_job_similarity
Revises: 003_voice_reference_text
Create Date: 2026-04-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_job_similarity"
down_revision: str | None = "003_voice_reference_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # tts_jobs: store the cosine similarity (in [-1, 1]) between the cloned
    # voice's reference and the generated audio. Populated by an async eval
    # task after generation completes; nullable because legacy rows and
    # non-cloning jobs never get scored.
    op.add_column(
        "tts_jobs",
        sa.Column("speaker_similarity", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tts_jobs", "speaker_similarity")
