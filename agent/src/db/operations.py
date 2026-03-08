"""Database helper operations for Ouro agent."""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    ActiveJob,
    AgentCost,
    AttributionLog,
    AuditLog,
    Credit,
    HistoricalData,
)


async def complete_job(
    db: AsyncSession,
    job_id: str,
    llm_cost_usd: float,
    compute_duration_s: float,
) -> None:
    """Move a job from active_jobs to historical_data atomically."""
    async with db.begin():
        job = await db.get(ActiveJob, job_id)
        if not job:
            raise ValueError(f"Active job {job_id} not found")

        await db.execute(
            insert(HistoricalData).values(
                id=job.id,
                slurm_job_id=job.slurm_job_id,
                submitter_address=job.submitter_address,
                payload=job.payload,
                status="completed",
                x402_tx_hash=job.x402_tx_hash,
                price_usdc=job.price_usdc,
                llm_cost_usd=llm_cost_usd,
                compute_duration_s=compute_duration_s,
                submitted_at=job.submitted_at,
            )
        )
        await db.delete(job)


async def fail_job(
    db: AsyncSession,
    job_id: str,
    reason: str,
    failure_stage: int | None = None,
    compute_duration_s: float = 0,
    fault: str | None = None,
) -> None:
    """Move a failed job from active_jobs to historical_data."""
    async with db.begin():
        job = await db.get(ActiveJob, job_id)
        if not job:
            return  # Already cleaned up
        payload = dict(job.payload or {}, failure_reason=reason)
        if failure_stage is not None:
            payload["failure_stage"] = failure_stage
        if fault is not None:
            payload["fault"] = fault
        await db.execute(
            insert(HistoricalData).values(
                id=job.id,
                slurm_job_id=job.slurm_job_id,
                submitter_address=job.submitter_address,
                payload=payload,
                status="failed",
                x402_tx_hash=job.x402_tx_hash,
                price_usdc=job.price_usdc,
                compute_duration_s=compute_duration_s,
                llm_cost_usd=0,
                submitted_at=job.submitted_at,
            )
        )
        await db.delete(job)


async def log_cost(
    db: AsyncSession,
    cost_type: str,
    amount_usd: float,
    detail: dict | None = None,
) -> None:
    cost = AgentCost(cost_type=cost_type, amount_usd=amount_usd, detail=detail)
    db.add(cost)
    await db.commit()


async def log_attribution(
    db: AsyncSession,
    tx_hash: str,
    codes: list[str],
    gas_used: int | None = None,
) -> None:
    entry = AttributionLog(tx_hash=tx_hash, codes=codes, gas_used=gas_used)
    db.add(entry)
    await db.commit()


async def issue_credit(
    db: AsyncSession,
    wallet_address: str,
    amount_usdc: float,
    reason: str,
) -> None:
    """Issue a USDC credit to a wallet (e.g. after a failed job)."""
    credit = Credit(
        wallet_address=wallet_address.lower(),
        amount_usdc=amount_usdc,
        reason=reason,
    )
    db.add(credit)
    await db.commit()


async def get_available_credit(db: AsyncSession, wallet_address: str) -> float:
    """Sum of unredeemed credits for a wallet."""
    result = await db.execute(
        select(func.coalesce(func.sum(Credit.amount_usdc), 0)).where(
            Credit.wallet_address == wallet_address.lower(),
            Credit.redeemed.is_(False),
        )
    )
    return float(result.scalar_one())


async def redeem_credits(
    db: AsyncSession, wallet_address: str, amount_usdc: float
) -> None:
    """Mark credits as redeemed up to the given amount (oldest first)."""
    remaining = amount_usdc
    result = await db.execute(
        select(Credit)
        .where(
            Credit.wallet_address == wallet_address.lower(),
            Credit.redeemed.is_(False),
        )
        .order_by(Credit.created_at)
        .with_for_update()
    )
    for credit in result.scalars():
        if remaining <= 0:
            break
        credit.redeemed = True
        remaining -= float(credit.amount_usdc)
    await db.commit()


async def log_audit(
    db: AsyncSession,
    event_type: str,
    job_id: _uuid.UUID | str | None = None,
    wallet_address: str | None = None,
    amount_usdc: float | None = None,
    detail: dict | None = None,
) -> None:
    """Write a structured audit log entry."""
    entry = AuditLog(
        event_type=event_type,
        job_id=_uuid.UUID(str(job_id)) if job_id else None,
        wallet_address=wallet_address,
        amount_usdc=amount_usdc,
        detail=detail,
    )
    db.add(entry)
    await db.commit()
