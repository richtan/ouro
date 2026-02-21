from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.api.pricing as pricing_state
from src.agent.event_bus import EventBus
from src.chain.client import BaseChainClient
from src.config import settings
from src.db.models import ActiveJob, AgentCost, AttributionLog, HistoricalData, WalletSnapshot
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


async def autonomous_loop(
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    last_tx_time: datetime | None = None
    base_margin = settings.PRICE_MARGIN_MULTIPLIER
    cycle_count = 0

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
                    f"Cluster: {cluster_status['allocated_nodes']}/{cluster_status['total_nodes']} nodes active, "
                    f"status={cluster_status['status']}",
                )

                # 5. Periodic on-chain heartbeat (respects survival phase)
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

                # 6. Agent discovery via ERC-8004 (every 10 cycles)
                if cycle_count % 10 == 0:
                    try:
                        agent_count = await chain_client.get_erc8004_agent_count()
                        event_bus.emit(
                            "discovery",
                            f"ERC-8004 registry scan: {agent_count} agents registered. "
                            f"Ouro is discoverable for agent-to-agent compute commerce.",
                        )
                    except Exception:
                        pass

                cycle_count += 1

        except Exception as e:
            event_bus.emit("loop_error", f"Autonomous loop error (recovering): {e}")
            logger.exception("autonomous_loop error")

        await asyncio.sleep(60)
