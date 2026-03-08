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

        # Phase 5a: multi-file workspaces
        await conn.execute(text(
            "ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS job_payload JSONB"
        ))
        await conn.execute(text(
            "ALTER TABLE payment_sessions ALTER COLUMN script DROP NOT NULL"
        ))

        # Phase 5a: CHECK constraint — sessions must have script or job_payload
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'chk_session_has_content'
                ) THEN
                    ALTER TABLE payment_sessions ADD CONSTRAINT chk_session_has_content
                    CHECK (script IS NOT NULL OR job_payload IS NOT NULL);
                END IF;
            END $$;
        """))

        # Remove proof system columns (no longer used)
        await conn.execute(text(
            "ALTER TABLE historical_data DROP COLUMN IF EXISTS proof_tx_hash"
        ))
        await conn.execute(text(
            "ALTER TABLE historical_data DROP COLUMN IF EXISTS output_hash"
        ))
        await conn.execute(text(
            "ALTER TABLE historical_data DROP COLUMN IF EXISTS gas_paid_wei"
        ))
        await conn.execute(text(
            "ALTER TABLE historical_data DROP COLUMN IF EXISTS gas_paid_usd"
        ))
        await conn.execute(text(
            "ALTER TABLE historical_data DROP COLUMN IF EXISTS builder_reward_usd"
        ))
        await conn.execute(text(
            "ALTER TABLE active_jobs DROP COLUMN IF EXISTS client_builder_code"
        ))
        await conn.execute(text(
            "UPDATE historical_data SET status = 'completed' WHERE status = 'completed_no_proof'"
        ))

        # Performance indexes (Phase 4)
        logger.info("Running auto-migration: create performance indexes ...")
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_active_jobs_status_submitted "
            "ON active_jobs (status, submitted_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_active_jobs_submitter_lower "
            "ON active_jobs (lower(submitter_address))"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_historical_data_submitter_lower "
            "ON historical_data (lower(submitter_address))"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_agent_costs_type_created "
            "ON agent_costs (cost_type, created_at)"
        ))

    logger.info("Auto-migration complete.")
