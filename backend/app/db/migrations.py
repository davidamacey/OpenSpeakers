"""Auto-run Alembic migrations on startup.

Pattern from OpenTranscribe: detect current schema state and upgrade if needed.
"""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from app.core.database import engine

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Run pending Alembic migrations. Safe to call on every startup."""
    logger.info("Checking database migrations...")

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()

    if current_rev is None:
        logger.info("Fresh database — running all migrations")
    else:
        logger.info("Current schema revision: %s", current_rev)

    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete")
