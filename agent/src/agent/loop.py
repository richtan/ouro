from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.api.pricing as pricing_state
from src.agent.event_bus import EventBus
from src.chain.client import BaseChainClient
from src.config import settings
from src.db.models import ActiveJob, AgentCost, AttributionLog, HistoricalData, StorageQuota, WalletSnapshot
from src.slurm.client import SlurmClient

logger = logging.getLogger(__name__)


async def _get_sustainability_stats(db: AsyncSession, hours: int = 24) -> dict:
    interval = text(f"now() - interval '{hours} hours'")

    revenue_q = await db.execute(
        select(func.coalesce(func.sum(HistoricalData.price_usdc), 0)).where(
            HistoricalData.completed_at >= interval
        )
    )
    revenue = float(revenue_q.scalar_one())

    costs_q = await db.execute(
        select(func.coalesce(func.sum(AgentCost.amount_usd), 0)).where(
            AgentCost.created_at >= interval
        )
    )
    costs = float(costs_q.scalar_one())

    ratio = revenue / costs if costs > 0 else float("inf")
    return {"revenue": revenue, "costs": costs, "net_pnl": revenue - costs, "ratio": ratio}


async def _get_last_attribution_time(db: AsyncSession) -> datetime | None:
    result = await db.execute(select(func.max(AttributionLog.created_at)))
    return result.scalar_one_or_none()


async def _get_jobs_last_hour(db: AsyncSession) -> int:
    interval = text("now() - interval '1 hour'")
    active_q = await db.execute(
        select(func.count(ActiveJob.id)).where(ActiveJob.submitted_at >= interval)
    )
    hist_q = await db.execute(
        select(func.count(HistoricalData.id)).where(HistoricalData.submitted_at >= interval)
    )
    return int(active_q.scalar_one()) + int(hist_q.scalar_one())


_last_storage_cleanup: datetime | None = None


async def _storage_cleanup(
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Check for inactive storage and clean up expired volumes. Runs daily."""
    global _last_storage_cleanup
    now = datetime.now(timezone.utc)

    # Only run once per 24 hours
    if _last_storage_cleanup and (now - _last_storage_cleanup).total_seconds() < 86400:
        return
    _last_storage_cleanup = now

    ttl_days = settings.STORAGE_TTL_DAYS
    warning_threshold = now - timedelta(days=ttl_days - 30)  # warn at 60 days
    delete_threshold = now - timedelta(days=ttl_days)  # delete at 90 days

    async with session_maker() as db:
        result = await db.execute(
            select(StorageQuota).where(
                StorageQuota.last_accessed_at < warning_threshold
            )
        )
        stale_quotas = result.scalars().all()

        for quota in stale_quotas:
            days_inactive = (now - quota.last_accessed_at).days

            if quota.last_accessed_at < delete_threshold:
                try:
                    locked = await db.execute(
                        select(StorageQuota)
                        .where(StorageQuota.wallet_address == quota.wallet_address)
                        .with_for_update()
                    )
                    fresh = locked.scalar_one_or_none()
                    if not fresh or fresh.last_accessed_at >= delete_threshold:
                        await db.rollback()
                        continue

                    deleted = await slurm_client.delete_wallet_storage(quota.wallet_address)
                    if deleted:
                        fresh.tier = "expired"
                        fresh.used_bytes = 0
                        fresh.file_count = 0
                        await db.commit()
                        event_bus.emit(
                            "storage",
                            f"Storage deleted for {quota.wallet_address[:10]}... "
                            f"({days_inactive} days inactive, TTL expired)",
                        )
                    else:
                        await db.rollback()
                    logger.info(
                        "Storage TTL cleanup for %s: deleted=%s (%d days inactive)",
                        quota.wallet_address, deleted, days_inactive,
                    )
                except Exception as e:
                    await db.rollback()
                    logger.warning("Storage cleanup failed for %s: %s", quota.wallet_address, e)
            else:
                event_bus.emit(
                    "storage",
                    f"Storage warning: {quota.wallet_address[:10]}... inactive for {days_inactive} days "
                    f"(expires in {ttl_days - days_inactive} days)",
                )

        if stale_quotas:
            logger.info("Storage cleanup check: %d stale quotas found", len(stale_quotas))


async def autonomous_loop(
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    last_tx_time: datetime | None = None
    base_margin = settings.PRICE_MARGIN_MULTIPLIER
    cycle_count = 0

    scaler = None
    if settings.AUTO_SCALING_ENABLED:
        from src.slurm.scaler import AutoScaler
        scaler = AutoScaler()

    while True:
        try:
            async with session_maker() as db:
                # 1. Snapshot wallet balances
                eth_bal, usdc_bal = await chain_client.get_balances()
                eth_price = await chain_client.get_eth_price_usd()
                eth_bal_display = float(chain_client.w3.from_wei(eth_bal, "ether"))

                snapshot = WalletSnapshot(
                    eth_balance=eth_bal,
                    usdc_balance=usdc_bal,
                    eth_price_usd=eth_price,
                )
                db.add(snapshot)
                await db.commit()

                event_bus.emit(
                    "wallet",
                    f"Balance: {eth_bal_display:.4f} ETH, {usdc_bal:.2f} USDC",
                )

                # 2. Four-phase survival engine
                stats = await _get_sustainability_stats(db)
                old_phase = pricing_state.current_phase
                new_phase = pricing_state.compute_phase(stats["ratio"])
                pricing_state.apply_phase(new_phase, base_margin)

                if new_phase != old_phase:
                    event_bus.emit(
                        "survival",
                        f"Phase transition: {old_phase} -> {new_phase} "
                        f"(ratio={stats['ratio']:.2f}, margin={pricing_state.current_margin:.2f}x, "
                        f"heartbeat={'off' if pricing_state.heartbeat_interval_min == 0 else f'{pricing_state.heartbeat_interval_min}min'})",
                    )

                event_bus.emit(
                    "pricing",
                    f"[{new_phase}] P&L: revenue=${stats['revenue']:.4f}, costs=${stats['costs']:.4f}, "
                    f"net=${stats['net_pnl']:.4f}, ratio={stats['ratio']:.2f}x, "
                    f"margin={pricing_state.current_margin:.2f}x",
                )

                # 3. Elastic demand pricing
                jobs_count = await _get_jobs_last_hour(db)
                old_demand = pricing_state.demand_multiplier
                pricing_state.update_demand(jobs_count)
                if abs(pricing_state.demand_multiplier - old_demand) > 0.01:
                    event_bus.emit(
                        "demand",
                        f"Demand adjusted: {jobs_count} jobs/hr -> multiplier={pricing_state.demand_multiplier:.2f}x "
                        f"(was {old_demand:.2f}x)",
                    )

                # 4. Check Slurm cluster health
                cluster_status = await slurm_client.get_cluster_info()
                event_bus.emit(
                    "cluster",
                    f"Cluster: {cluster_status.get('available_cpus', 0)} CPUs available, "
                    f"{cluster_status['allocated_nodes']}/{cluster_status['total_nodes']} nodes active, "
                    f"status={cluster_status['status']}",
                )

                # 4b. Elastic auto-scaling
                if scaler:
                    scaling_event = await scaler.evaluate_and_act(cluster_status, db)
                    if scaling_event:
                        from src.db.models import ScalingEvent as ScalingEventModel
                        event_bus.emit(
                            "scaling",
                            f"[{scaling_event.action}] {scaling_event.node_name}: {scaling_event.reason}",
                        )
                        db.add(ScalingEventModel(
                            event_type=scaling_event.action,
                            node_name=scaling_event.node_name,
                            reason=scaling_event.reason,
                        ))
                        await db.commit()

                # 5. Storage TTL cleanup (runs daily)
                try:
                    await _storage_cleanup(slurm_client, session_maker, event_bus)
                except Exception as e:
                    logger.warning("Storage cleanup error: %s", e)

                # 6. Periodic on-chain heartbeat (respects survival phase)
                now = datetime.now(timezone.utc)
                if last_tx_time is None:
                    last_tx_time = await _get_last_attribution_time(db) or now

                hb_interval = pricing_state.heartbeat_interval_min
                if hb_interval > 0:
                    minutes_since = (now - last_tx_time).total_seconds() / 60
                    if minutes_since > hb_interval:
                        try:
                            from src.db.operations import log_attribution, log_cost

                            result = await chain_client.send_heartbeat()
                            await log_cost(db, "gas", result.gas_cost_usd, {
                                "tx_hash": result.tx_hash, "type": "heartbeat",
                            })
                            await log_attribution(
                                db, result.tx_hash, result.codes, result.gas_cost_wei,
                            )
                            last_tx_time = now
                            event_bus.emit("heartbeat", f"On-chain heartbeat sent: tx={result.tx_hash}")
                        except Exception as e:
                            event_bus.emit("heartbeat_error", f"Heartbeat failed: {e}")
                elif cycle_count % 5 == 0:
                    event_bus.emit(
                        "heartbeat",
                        f"Heartbeat paused (phase={new_phase}, saving gas)",
                    )

                cycle_count += 1

        except Exception as e:
            event_bus.emit("loop_error", f"Autonomous loop error (recovering): {e}")
            logger.exception("autonomous_loop error")

        await asyncio.sleep(60)
