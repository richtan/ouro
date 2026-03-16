"""Job processor: picks up pending ActiveJobs, runs them through the
deterministic fast path, and falls back to the LLM agent on failure."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.agent.classifier import classify_failure
from src.agent.event_bus import EventBus
from src.agent.oracle import JobResult, OracleDeps, oracle_agent, process_job_fast
from src.api.pricing import calculate_unused_compute_credit, estimate_llm_cost, verify_job_profit
from src.chain.client import BaseChainClient
from src.config import settings
from src.db.models import ActiveJob
from src.agent.webhooks import build_webhook_payload, deliver_webhook
from src.db.operations import complete_job, fail_job, issue_credit, log_audit, log_cost
from src.slurm.client import SlurmClient

logger = logging.getLogger(__name__)

FAST_PATH_TIMEOUT_S = 900  # 10-min image build + 5-min Slurm poll
LLM_FALLBACK_TIMEOUT_S = 900
MAX_RETRIES = 2
MAX_CONCURRENT_JOBS = 3

TRANSIENT_ERRORS = ("timeout", "connection", "unreachable", "slurm_error")


def _fire_webhook_if_configured(
    job_id: str,
    status: str,
    payload: dict,
    price_usdc: float,
    submitter_address: str | None,
    submitted_at: datetime | None,
    compute_duration_s: float,
    event_bus: EventBus | None = None,
) -> None:
    """Fire webhook as background task if webhook_url is in payload."""
    webhook_url = (payload or {}).get("webhook_url")
    if not webhook_url:
        return
    wh_payload = build_webhook_payload(
        job_id=job_id,
        status=status,
        payload=payload,
        price_usdc=price_usdc,
        submitter_address=submitter_address,
        submitted_at=submitted_at,
        compute_duration_s=compute_duration_s,
    )
    asyncio.create_task(deliver_webhook(webhook_url, wh_payload, event_bus=event_bus))


def _is_transient(error_msg: str) -> bool:
    lower = error_msg.lower()
    return any(tok in lower for tok in TRANSIENT_ERRORS)


async def recover_stuck_jobs(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Reset orphaned jobs on startup.

    - processing: reset to pending (safe retry, not yet submitted to Slurm)
    - running: mark failed (already in Slurm, we lost the in-flight context)
    """
    async with session_maker() as db:
        proc_result = await db.execute(
            update(ActiveJob)
            .where(ActiveJob.status == "processing")
            .values(status="pending")
            .returning(ActiveJob.id)
        )
        recovered = proc_result.scalars().all()

        run_result = await db.execute(
            select(ActiveJob).where(ActiveJob.status == "running")
        )
        running_jobs = run_result.scalars().all()
        for rj in running_jobs:
            await fail_job(db, str(rj.id), "recovered_on_startup", failure_stage=3, fault="platform_error")
        failed = [rj.id for rj in running_jobs]

        await db.commit()

        # Issue credits for orphaned running jobs (platform crashed = platform_error)
        for rj in running_jobs:
            if rj.submitter_address and float(rj.price_usdc) > 0:
                try:
                    async with session_maker() as credit_db:
                        await issue_credit(
                            credit_db,
                            wallet_address=rj.submitter_address,
                            amount_usdc=float(rj.price_usdc),
                            reason=f"job_failed:{rj.id}",
                        )
                        await log_audit(
                            credit_db,
                            event_type="credit_issued",
                            job_id=rj.id,
                            wallet_address=rj.submitter_address,
                            amount_usdc=float(rj.price_usdc),
                            detail={"reason": "recovered_on_startup", "fault": "platform_error"},
                        )
                except Exception:
                    logger.exception("Failed to issue credit for recovered job %s", rj.id)

        if recovered:
            event_bus.emit("system", f"Recovered {len(recovered)} stuck processing jobs (-> pending)")
            logger.info("Recovered processing -> pending: %s", [str(r)[:8] for r in recovered])
        if failed:
            event_bus.emit("system", f"Marked {len(failed)} orphaned running jobs as failed")
            logger.info("Orphaned running -> failed: %s", [str(r)[:8] for r in failed])

        # Fire webhooks for recovered running jobs (after commit + credit issuance)
        for rj in running_jobs:
            _fire_webhook_if_configured(
                job_id=str(rj.id),
                status="failed",
                payload=dict(rj.payload or {}, failure_reason="recovered_on_startup", fault="platform_error"),
                price_usdc=float(rj.price_usdc),
                submitter_address=rj.submitter_address,
                submitted_at=rj.submitted_at,
                compute_duration_s=0,
                event_bus=event_bus,
            )


async def _mark_failed(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    job: ActiveJob,
    reason: str,
    failure_stage: int | None = None,
    compute_duration_s: float = 0,
    exit_code: int | None = None,
    slurm_state: str | None = None,
) -> None:
    """Mark a job as failed and issue a credit only for platform errors."""
    try:
        fault = classify_failure(failure_stage, reason, exit_code=exit_code, slurm_state=slurm_state)

        # Persist event_log before archival (re-read to avoid overwriting output_text)
        try:
            async with session_maker() as db:
                fresh = await db.get(ActiveJob, str(job.id))
                if fresh:
                    updated = dict(fresh.payload or {}, event_log=event_bus.get_job_events(str(job.id)))
                    await db.execute(
                        update(ActiveJob).where(ActiveJob.id == job.id).values(payload=updated)
                    )
                    await db.commit()
        except Exception:
            logger.warning("Failed to persist event_log for job %s", job.id)

        async with session_maker() as db:
            await fail_job(
                db, str(job.id), reason,
                failure_stage=failure_stage,
                compute_duration_s=compute_duration_s,
                fault=fault,
            )

        # Log compute infrastructure cost for failed jobs
        if compute_duration_s > 0:
            try:
                cpus = (job.payload or {}).get("cpus", 1)
                compute_infra_cost = cpus * (compute_duration_s / 60) * settings.INFRA_COST_PER_CPU_MINUTE
                async with session_maker() as db:
                    await log_cost(
                        db,
                        cost_type="compute",
                        amount_usd=compute_infra_cost,
                        detail={"job_id": str(job.id), "cpus": cpus, "duration_s": compute_duration_s, "fault": fault},
                    )
            except Exception:
                logger.exception("Failed to log compute cost for failed job %s", job.id)

        if fault == "platform_error" and job.submitter_address and float(job.price_usdc) > 0:
            async with session_maker() as db:
                await issue_credit(
                    db,
                    wallet_address=job.submitter_address,
                    amount_usdc=float(job.price_usdc),
                    reason=f"job_failed:{job.id}",
                )
                await log_audit(
                    db,
                    event_type="credit_issued",
                    job_id=job.id,
                    wallet_address=job.submitter_address,
                    amount_usdc=float(job.price_usdc),
                    detail={"reason": reason, "fault": fault},
                )

        event_bus.emit(
            "job",
            f"Job {str(job.id)[:8]} failed ({fault}): {reason}",
            job_id=str(job.id),
        )

        _fire_webhook_if_configured(
            job_id=str(job.id),
            status="failed",
            payload=dict(job.payload or {}, failure_reason=reason, fault=fault),
            price_usdc=float(job.price_usdc),
            submitter_address=job.submitter_address,
            submitted_at=job.submitted_at,
            compute_duration_s=compute_duration_s,
            event_bus=event_bus,
        )
    except Exception:
        logger.exception("failed to mark job %s as failed", job.id)


async def _maybe_retry(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    job: ActiveJob,
    reason: str,
) -> bool:
    """If the failure is transient and retries remain, reset to pending. Returns True if retried."""
    retry_count = job.retry_count or 0
    if retry_count >= MAX_RETRIES or not _is_transient(reason):
        return False

    try:
        async with session_maker() as db:
            await db.execute(
                update(ActiveJob)
                .where(ActiveJob.id == job.id)
                .values(status="pending", retry_count=retry_count + 1)
            )
            await db.commit()
        event_bus.emit(
            "job",
            f"Job {str(job.id)[:8]} retrying ({retry_count + 1}/{MAX_RETRIES}): {reason}",
            job_id=str(job.id),
        )
        return True
    except Exception:
        logger.exception("failed to retry job %s", job.id)
        return False


async def _finalize_success(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    job: ActiveJob,
    job_result: JobResult,
    deps: OracleDeps,
    llm_cost_usd: float,
    compute_duration_s: float,
) -> None:
    """Archive a successful job and log profitability."""
    async with session_maker() as db:
        updated_payload = dict(job.payload)
        if deps.captured_output or deps.captured_error:
            import json
            updated_payload["output_text"] = json.dumps({
                "output": deps.captured_output[:10000],
                "error_output": deps.captured_error[:5000],
            })
        updated_payload["event_log"] = event_bus.get_job_events(str(job.id))
        await db.execute(
            update(ActiveJob)
            .where(ActiveJob.id == job.id)
            .values(payload=updated_payload)
        )
        await db.commit()

        await complete_job(
            db=db,
            job_id=str(job.id),
            llm_cost_usd=llm_cost_usd,
            compute_duration_s=compute_duration_s,
        )

        await log_audit(
            db,
            event_type="job_completed",
            job_id=job.id,
            wallet_address=job.submitter_address,
            amount_usdc=float(job.price_usdc),
            detail={
                "duration_s": compute_duration_s,
            },
        )

    pv = verify_job_profit(
        job_id=str(job.id),
        price_charged_usd=float(job.price_usdc),
        llm_cost_usd=llm_cost_usd,
        compute_duration_s=compute_duration_s,
        cpus=deps.cpus,
    )
    event_bus.emit(
        "profit",
        f"Job {str(job.id)[:8]} — "
        f"charged: ${pv.price_charged_usd:.4f}, "
        f"actual cost: ${pv.actual_cost_usd:.4f}, "
        f"profit: ${pv.actual_profit_usd:.4f} ({pv.actual_profit_pct:.1f}%) "
        f"{'PROFITABLE' if pv.profitable else 'LOSS'}",
        job_id=str(job.id),
    )
    if not pv.profitable:
        logger.warning("Job %s completed at a LOSS: %s", job.id, pv)

    # Log compute infrastructure cost
    try:
        compute_infra_cost = deps.cpus * (compute_duration_s / 60) * settings.INFRA_COST_PER_CPU_MINUTE
        async with session_maker() as db:
            await log_cost(
                db,
                cost_type="compute",
                amount_usd=compute_infra_cost,
                detail={"job_id": str(job.id), "cpus": deps.cpus, "duration_s": compute_duration_s},
            )
    except Exception:
        logger.exception("Failed to log compute cost for job %s", job.id)

    # Issue credit for unused compute time (proportional to marked-up price)
    try:
        cost_floor = (job.payload or {}).get("cost_floor", 0)
        compute_cost = (job.payload or {}).get("compute_cost", 0)
        if cost_floor > 0 and compute_cost > 0:
            price_usdc = float(job.price_usdc)
            time_limit_min = (job.payload or {}).get("time_limit_min", 0)
            credit = calculate_unused_compute_credit(
                price_usdc, cost_floor, compute_cost, time_limit_min, compute_duration_s,
            )
            if credit > 0 and job.submitter_address:
                async with session_maker() as db:
                    await issue_credit(
                        db,
                        wallet_address=job.submitter_address,
                        amount_usdc=credit,
                        reason=f"unused_compute:{job.id}",
                    )
                    await log_audit(
                        db,
                        event_type="credit_issued",
                        job_id=job.id,
                        wallet_address=job.submitter_address,
                        amount_usdc=credit,
                        detail={"reason": "unused_compute", "time_limit_min": time_limit_min, "duration_s": compute_duration_s},
                    )
                event_bus.emit(
                    "credit",
                    f"Unused compute credit: ${credit:.4f} to {job.submitter_address[:10]}... "
                    f"(used {compute_duration_s:.0f}s of {time_limit_min * 60}s)",
                    job_id=str(job.id),
                )
    except Exception:
        logger.exception("Failed to issue unused compute credit for job %s", job.id)

    event_bus.emit("job", f"Job {str(job.id)[:8]} completed and archived", job_id=str(job.id))

    _fire_webhook_if_configured(
        job_id=str(job.id),
        status="completed",
        payload=updated_payload,
        price_usdc=float(job.price_usdc),
        submitter_address=job.submitter_address,
        submitted_at=job.submitted_at,
        compute_duration_s=compute_duration_s,
        event_bus=event_bus,
    )


async def _process_one_job(
    job: ActiveJob,
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    semaphore: asyncio.Semaphore,
) -> None:
    """Process a single job. Runs as a concurrent task; releases semaphore when done."""
    try:
        event_bus.emit("agent", f"Processing job {str(job.id)[:8]} (fast path)", job_id=str(job.id))
        job_start = time.monotonic()
        llm_cost_usd = 0.0

        async with session_maker() as db:
            payload = job.payload or {}

            # Legacy normalization: old script-mode jobs have no workspace_path.
            # Create workspace at processing time so the unified path works.
            workspace_path = payload.get("workspace_path")
            entrypoint = payload.get("entrypoint")
            if not workspace_path and payload.get("script"):
                script = payload["script"]
                files = [{"path": "job.sh", "content": script}]
                workspace_path = await slurm_client.create_workspace(str(job.id), files)
                entrypoint = "job.sh"
                event_bus.emit("agent", f"Legacy job {str(job.id)[:8]}: created workspace from inline script", job_id=str(job.id))

            deps = OracleDeps(
                job_id=str(job.id),
                workspace_path=workspace_path or "",
                entrypoint=entrypoint or "",
                image=payload.get("image", "ouro-ubuntu"),
                partition=payload.get("partition", "default"),
                cpus=payload.get("cpus", 1),
                time_limit_min=payload.get("time_limit_min", 1),
                slurm_client=slurm_client,
                chain_client=chain_client,
                db=db,
                event_bus=event_bus,
                dockerfile_content=payload.get("dockerfile_content"),
            )

            job_result = await asyncio.wait_for(
                process_job_fast(deps),
                timeout=FAST_PATH_TIMEOUT_S,
            )

        compute_duration_s = time.monotonic() - job_start

        if job_result and job_result.status == "completed":
            await _finalize_success(
                session_maker, event_bus, job, job_result,
                deps, llm_cost_usd, compute_duration_s,
            )
        else:
            reason = (
                deps.captured_error
                or (job_result.status if job_result else "no result")
            )
            failure_stage = job_result.failure_stage if job_result else 3
            # Store captured output/error even for failed jobs
            if deps.captured_output or deps.captured_error:
                import json
                output_text = json.dumps({
                    "output": deps.captured_output[:10000],
                    "error_output": deps.captured_error[:5000],
                })
                try:
                    async with session_maker() as db:
                        await db.execute(
                            update(ActiveJob)
                            .where(ActiveJob.id == job.id)
                            .values(payload=dict(job.payload, output_text=output_text))
                        )
                        await db.commit()
                except Exception:
                    logger.warning("Failed to store error output for job %s", job.id)
            retried = await _maybe_retry(session_maker, event_bus, job, reason)
            if not retried:
                await _mark_failed(
                    session_maker, event_bus, job, reason,
                    failure_stage=failure_stage,
                    compute_duration_s=time.monotonic() - job_start,
                    exit_code=job_result.exit_code if job_result else None,
                    slurm_state=job_result.slurm_state if job_result else None,
                )

    except asyncio.TimeoutError:
        reason = f"timeout after {FAST_PATH_TIMEOUT_S}s"
        event_bus.emit("agent_error", f"Job {str(job.id)[:8]} {reason}", job_id=str(job.id))
        logger.error("Fast path timed out for job %s", job.id)
        retried = await _maybe_retry(session_maker, event_bus, job, reason)
        if not retried:
            await _mark_failed(session_maker, event_bus, job, reason, failure_stage=3, compute_duration_s=time.monotonic() - job_start)
    except Exception as e:
        reason = str(e)
        event_bus.emit("agent_error", f"Job {str(job.id)[:8]} error: {reason}", job_id=str(job.id))
        logger.exception("job processor error for %s", job.id)
        retried = await _maybe_retry(session_maker, event_bus, job, reason)
        if not retried:
            await _mark_failed(session_maker, event_bus, job, reason, failure_stage=3, compute_duration_s=time.monotonic() - job_start)
    finally:
        semaphore.release()


async def process_pending_jobs(
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Background loop: pick up pending jobs and process up to MAX_CONCURRENT_JOBS concurrently."""
    await recover_stuck_jobs(session_maker, event_bus)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    while True:
        await semaphore.acquire()
        try:
            async with session_maker() as db:
                result = await db.execute(
                    select(ActiveJob)
                    .where(ActiveJob.status == "pending")
                    .order_by(ActiveJob.submitted_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                job = result.scalar_one_or_none()

                if job is None:
                    semaphore.release()
                    await asyncio.sleep(5)
                    continue

                await db.execute(
                    update(ActiveJob)
                    .where(ActiveJob.id == job.id)
                    .values(status="processing")
                )
                await db.commit()

            # Spawn concurrent task — semaphore is released in _process_one_job's finally
            asyncio.create_task(_process_one_job(
                job, chain_client, slurm_client, session_maker, event_bus, semaphore,
            ))

        except Exception as e:
            semaphore.release()
            logger.exception("Error picking up job: %s", e)
            event_bus.emit("agent_error", f"Job pickup error: {e}")
            await asyncio.sleep(10)
