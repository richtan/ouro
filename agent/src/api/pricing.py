from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import AgentCost

logger = logging.getLogger(__name__)

ATTRIBUTION_DISCOUNT = 0.10
MIN_PRICE_USD = 0.01
DEFAULT_GAS_COST_USD = 0.002
DEFAULT_LLM_COST_USD = 0.008
COST_SAFETY_FACTOR = 1.25

current_margin: float = settings.PRICE_MARGIN_MULTIPLIER
current_phase: str = "OPTIMAL"
heartbeat_interval_min: int = 60
demand_multiplier: float = 1.0
jobs_last_hour: int = 0

PHASE_THRESHOLDS = {
    "OPTIMAL": 1.5,
    "CAUTIOUS": 1.0,
    "SURVIVAL": 0.5,
    "CRITICAL": 0.0,
}

PHASE_CONFIG = {
    "OPTIMAL": {"margin_factor": 1.0, "heartbeat_min": 60},
    "CAUTIOUS": {"margin_factor": 1.1, "heartbeat_min": 120},
    "SURVIVAL": {"margin_factor": 1.3, "heartbeat_min": 0},
    "CRITICAL": {"margin_factor": 3.0, "heartbeat_min": 0},
}


@dataclass
class PriceQuote:
    price_usd: float
    price_str: str
    cost_floor_usd: float
    profit_usd: float
    profit_pct: float
    guaranteed_profitable: bool
    breakdown: dict


@dataclass
class ProfitVerification:
    job_id: str
    price_charged_usd: float
    actual_cost_usd: float
    actual_profit_usd: float
    actual_profit_pct: float
    profitable: bool


def compute_phase(sustainability_ratio: float) -> str:
    if sustainability_ratio >= PHASE_THRESHOLDS["OPTIMAL"]:
        return "OPTIMAL"
    if sustainability_ratio >= PHASE_THRESHOLDS["CAUTIOUS"]:
        return "CAUTIOUS"
    if sustainability_ratio >= PHASE_THRESHOLDS["SURVIVAL"]:
        return "SURVIVAL"
    return "CRITICAL"


def apply_phase(phase: str, base_margin: float) -> None:
    global current_phase, current_margin, heartbeat_interval_min
    config = PHASE_CONFIG[phase]
    current_phase = phase
    current_margin = base_margin * config["margin_factor"]
    heartbeat_interval_min = config["heartbeat_min"]


def update_demand(jobs_count: int) -> None:
    global demand_multiplier, jobs_last_hour
    jobs_last_hour = jobs_count
    if jobs_count == 0:
        demand_multiplier = 0.8
    elif jobs_count <= 3:
        demand_multiplier = 1.0
    else:
        demand_multiplier = 1.0 + (jobs_count - 3) * 0.15


async def get_cost_upper_bound(
    db: AsyncSession, cost_type: str, hours: int = 24
) -> float | None:
    """Return the MAX observed cost as a conservative upper bound (not average)."""
    result = await db.execute(
        select(func.max(AgentCost.amount_usd)).where(
            AgentCost.cost_type == cost_type,
            AgentCost.created_at >= text(f"now() - interval '{hours} hours'"),
        )
    )
    val = result.scalar_one_or_none()
    return float(val) if val is not None else None


async def calculate_price(
    db: AsyncSession,
    requested_nodes: int,
    time_limit_min: int,
    client_builder_code: str | None = None,
) -> PriceQuote:
    max_gas = await get_cost_upper_bound(db, "gas") or DEFAULT_GAS_COST_USD
    max_llm = await get_cost_upper_bound(db, "llm_inference") or DEFAULT_LLM_COST_USD

    gas_ub = max_gas * COST_SAFETY_FACTOR
    llm_ub = max_llm * COST_SAFETY_FACTOR
    compute_cost = requested_nodes * time_limit_min * settings.INFRA_COST_PER_NODE_MINUTE

    cost_floor = gas_ub + llm_ub + compute_cost

    margin_price = cost_floor * current_margin * demand_multiplier
    min_profit_price = cost_floor * (1 + settings.MIN_PROFIT_PCT)
    price = max(margin_price, min_profit_price, MIN_PRICE_USD)

    if client_builder_code:
        discounted = price * (1 - ATTRIBUTION_DISCOUNT)
        price = max(discounted, min_profit_price)

    profit = price - cost_floor
    profit_pct = (profit / cost_floor * 100) if cost_floor > 0 else float("inf")

    return PriceQuote(
        price_usd=price,
        price_str=f"${price:.4f}",
        cost_floor_usd=cost_floor,
        profit_usd=profit,
        profit_pct=profit_pct,
        guaranteed_profitable=price > cost_floor,
        breakdown={
            "gas_upper_bound": round(gas_ub, 6),
            "llm_upper_bound": round(llm_ub, 6),
            "compute_cost": round(compute_cost, 6),
            "cost_floor": round(cost_floor, 6),
            "margin_multiplier": current_margin,
            "demand_multiplier": demand_multiplier,
            "phase": current_phase,
            "min_profit_pct": settings.MIN_PROFIT_PCT,
            "safety_factor": COST_SAFETY_FACTOR,
            "builder_discount_applied": bool(client_builder_code),
        },
    )


def verify_job_profit(
    job_id: str,
    price_charged_usd: float,
    gas_cost_usd: float,
    llm_cost_usd: float,
    compute_duration_s: float = 0.0,
    nodes: int = 1,
) -> ProfitVerification:
    infra_cost = nodes * (compute_duration_s / 60) * settings.INFRA_COST_PER_NODE_MINUTE
    actual_cost = gas_cost_usd + llm_cost_usd + infra_cost
    profit = price_charged_usd - actual_cost
    profit_pct = (profit / actual_cost * 100) if actual_cost > 0 else float("inf")

    return ProfitVerification(
        job_id=job_id,
        price_charged_usd=price_charged_usd,
        actual_cost_usd=actual_cost,
        actual_profit_usd=profit,
        actual_profit_pct=profit_pct,
        profitable=profit > 0,
    )


def estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1_000_000) * settings.LLM_PRICE_INPUT_PER_M
    output_cost = (output_tokens / 1_000_000) * settings.LLM_PRICE_OUTPUT_PER_M
    return input_cost + output_cost
