"""Database helper operations for Ouro agent."""

from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ActiveJob, AgentCost, AttributionLog, HistoricalData


async def complete_job(
    db: AsyncSession,
    job_id: str,
    proof_tx: str,
    output_hash: bytes,
    gas_cost_usd: float,
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
                gas_paid_usd=gas_cost_usd,
                output_hash=output_hash,
                proof_tx_hash=proof_tx,
                llm_cost_usd=llm_cost_usd,
                compute_duration_s=compute_duration_s,
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
