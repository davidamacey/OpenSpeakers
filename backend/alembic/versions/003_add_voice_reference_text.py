"""Add reference transcript columns to voice_profiles.

Revision ID: 003_voice_reference_text
Revises: 002_cancel_batch_voice
Create Date: 2026-04-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_voice_reference_text"
down_revision: str | None = "002_cancel_batch_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # voice_profiles: capture the reference transcript (auto-detected by
    # faster-whisper or manually entered) plus its workflow status and the
    # detected language code. Nullable text + nullable language preserves
    # backwards compatibility with existing rows.
    op.add_column(
        "voice_profiles",
        sa.Column("reference_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "voice_profiles",
        sa.Column(
            "reference_text_status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "voice_profiles",
        sa.Column("reference_language", sa.String(8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("voice_profiles", "reference_language")
    op.drop_column("voice_profiles", "reference_text_status")
    op.drop_column("voice_profiles", "reference_text")
