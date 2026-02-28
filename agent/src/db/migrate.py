"""Lightweight auto-migration that runs on every agent startup.

Uses create_all (checkfirst=True) so new tables are created automatically,
and ALTER TABLE ... ADD COLUMN IF NOT EXISTS for columns added after the
initial schema deployment.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from src.db.models import Base

logger = logging.getLogger(__name__)


async def run_migrations(engine) -> None:
    async with engine.begin() as conn:
        logger.info("Running auto-migration: create_all (checkfirst=True) ...")
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

        logger.info("Running auto-migration: add missing columns ...")
        await conn.execute(text(
            "ALTER TABLE active_jobs ADD COLUMN IF NOT EXISTS submitter_address TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE historical_data ADD COLUMN IF NOT EXISTS submitter_address TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE active_jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"
        ))

    logger.info("Auto-migration complete.")
