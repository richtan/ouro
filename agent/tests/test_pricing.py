"""Tests for the pricing engine."""

from __future__ import annotations

import pytest

from src.api import pricing
from src.api.pricing import (
    UNUSED_COMPUTE_CREDIT_THRESHOLD,
    apply_phase,
    calculate_unused_compute_credit,
    compute_phase,
    estimate_llm_cost,
    update_demand,
    verify_job_profit,
)
from src.config import settings


@pytest.fixture(autouse=True)
def _reset_pricing_globals():
    """Save and restore pricing module globals between tests."""
    orig = {
        "current_margin": pricing.current_margin,
        "current_phase": pricing.current_phase,
        "heartbeat_interval_min": pricing.heartbeat_interval_min,
        "demand_multiplier": pricing.demand_multiplier,
        "jobs_last_hour": pricing.jobs_last_hour,
    }
    yield
    for k, v in orig.items():
        setattr(pricing, k, v)


# --- compute_phase ---


def test_compute_phase_optimal():
    assert compute_phase(2.0) == "OPTIMAL"


def test_compute_phase_cautious():
    assert compute_phase(1.2) == "CAUTIOUS"


def test_compute_phase_survival():
    assert compute_phase(0.7) == "SURVIVAL"


def test_compute_phase_critical():
    assert compute_phase(0.3) == "CRITICAL"


def test_compute_phase_boundaries():
    assert compute_phase(1.5) == "OPTIMAL"
    assert compute_phase(1.0) == "CAUTIOUS"
    assert compute_phase(0.5) == "SURVIVAL"
    assert compute_phase(0.0) == "CRITICAL"


# --- apply_phase ---


def test_apply_phase_sets_globals():
    apply_phase("CRITICAL", 1.5)
    assert pricing.current_phase == "CRITICAL"
    assert pricing.current_margin == 1.5 * 3.0  # 4.5
    assert pricing.heartbeat_interval_min == 0


def test_apply_phase_optimal():
    apply_phase("OPTIMAL", 1.5)
    assert pricing.current_margin == 1.5 * 1.0
    assert pricing.heartbeat_interval_min == 60


# --- update_demand ---


def test_update_demand_zero():
    update_demand(0)
    assert pricing.demand_multiplier == 0.8
    assert pricing.jobs_last_hour == 0


def test_update_demand_normal():
    update_demand(2)
    assert pricing.demand_multiplier == 1.0


def test_update_demand_high():
    update_demand(6)
    # 1.0 + (6-3)*0.15 = 1.45
    assert pricing.demand_multiplier == pytest.approx(1.45)


# --- verify_job_profit ---


def test_verify_profit_profitable():
    pv = verify_job_profit("job1", price_charged_usd=0.10, llm_cost_usd=0.01)
    assert pv.profitable is True
    assert pv.actual_profit_usd > 0


def test_verify_profit_loss():
    pv = verify_job_profit("job1", price_charged_usd=0.001, llm_cost_usd=0.05)
    assert pv.profitable is False
    assert pv.actual_profit_usd < 0


# --- estimate_llm_cost ---


def test_estimate_llm_cost():
    cost = estimate_llm_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    expected = settings.LLM_PRICE_INPUT_PER_M + settings.LLM_PRICE_OUTPUT_PER_M
    assert cost == pytest.approx(expected)


def test_estimate_llm_cost_zero_tokens():
    cost = estimate_llm_cost("gpt-4o-mini", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_compute_phase_negative_ratio():
    assert compute_phase(-1.0) == "CRITICAL"


# --- calculate_price (async, mocked DB) ---


async def test_calculate_price_with_defaults():
    """When DB returns no cost data, defaults are used."""
    from unittest.mock import AsyncMock, MagicMock

    from src.api.pricing import calculate_price

    db = AsyncMock()
    # get_cost_upper_bound returns None → defaults used
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    quote = await calculate_price(db, requested_cpus=1, time_limit_min=1)
    assert quote.price_usd >= pricing.MIN_PRICE_USD
    assert quote.guaranteed_profitable is True
    assert "gas_upper_bound" in quote.breakdown


async def test_calculate_price_with_real_costs():
    """When DB returns actual cost values, floor uses them."""
    from unittest.mock import AsyncMock, MagicMock

    from src.api.pricing import COST_SAFETY_FACTOR, calculate_price

    db = AsyncMock()
    mock_result = MagicMock()
    # First call (gas) returns 0.005, second call (llm) returns 0.02
    mock_result.scalar_one_or_none.side_effect = [0.005, 0.02]
    db.execute.return_value = mock_result

    quote = await calculate_price(db, requested_cpus=2, time_limit_min=10)
    # Verify cost floor includes safety factor
    expected_gas_ub = 0.005 * COST_SAFETY_FACTOR
    expected_llm_ub = 0.02 * COST_SAFETY_FACTOR
    assert quote.breakdown["gas_upper_bound"] == pytest.approx(expected_gas_ub, abs=1e-6)
    assert quote.breakdown["llm_upper_bound"] == pytest.approx(expected_llm_ub, abs=1e-6)


async def test_calculate_price_min_price_floor():
    """When computed price < $0.01, floors at MIN_PRICE_USD."""
    from unittest.mock import AsyncMock, MagicMock

    from src.api.pricing import calculate_price

    # Set margin very low to produce a tiny price
    pricing.current_margin = 0.01
    pricing.demand_multiplier = 0.01

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    quote = await calculate_price(db, requested_cpus=1, time_limit_min=1)
    assert quote.price_usd >= pricing.MIN_PRICE_USD


async def test_calculate_price_multi_file_setup_cost():
    """Multi-file mode includes setup cost in breakdown."""
    from unittest.mock import AsyncMock, MagicMock

    from src.api.pricing import SETUP_COST_BY_MODE, calculate_price

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    quote_script = await calculate_price(db, 1, 1, "script")
    quote_multi = await calculate_price(db, 1, 1, "multi_file")

    assert quote_multi.breakdown["setup_cost"] == pytest.approx(SETUP_COST_BY_MODE["multi_file"])
    assert quote_multi.breakdown["submission_mode"] == "multi_file"
    assert quote_multi.cost_floor_usd > quote_script.cost_floor_usd


# --- calculate_unused_compute_credit ---


def test_unused_compute_credit_proportional():
    """Credit includes markup, not just raw compute cost."""
    # 1 CPU, 10 min requested, job completes in 2 min (120s)
    # cost_floor=$0.0145, compute_cost=$0.002, price=$0.022
    credit = calculate_unused_compute_credit(
        price_usdc=0.022,
        cost_floor=0.0145,
        compute_cost=0.002,
        time_limit_min=10,
        compute_duration_s=120,
    )
    # compute_fraction = 0.002 / 0.0145 ≈ 0.1379
    # compute_price_portion = 0.022 * 0.1379 ≈ 0.003034
    # unused_fraction = (600 - 120) / 600 = 0.8
    # credit = 0.003034 * 0.8 ≈ 0.002427
    assert credit > 0
    assert credit > 0.002  # more than raw compute savings ($0.0016)
    assert credit < 0.01   # but not unreasonably large


def test_unused_compute_credit_below_threshold():
    """Tiny savings below threshold returns 0."""
    credit = calculate_unused_compute_credit(
        price_usdc=0.01,
        cost_floor=0.008,
        compute_cost=0.0001,
        time_limit_min=1,
        compute_duration_s=50,  # only 10s unused out of 60
    )
    assert credit == 0.0


def test_unused_compute_credit_full_usage():
    """No unused time → no credit."""
    credit = calculate_unused_compute_credit(
        price_usdc=0.022,
        cost_floor=0.0145,
        compute_cost=0.002,
        time_limit_min=10,
        compute_duration_s=600,  # full 10 min
    )
    assert credit == 0.0


def test_unused_compute_credit_over_time():
    """Duration exceeding time_limit → no credit (max(0, ...) clamps)."""
    credit = calculate_unused_compute_credit(
        price_usdc=0.022,
        cost_floor=0.0145,
        compute_cost=0.002,
        time_limit_min=10,
        compute_duration_s=700,  # over 10 min
    )
    assert credit == 0.0


def test_unused_compute_credit_multi_cpu():
    """Multi-CPU jobs: compute_cost scales with CPUs, so credit scales too."""
    # 4 CPUs → compute_cost is 4× higher
    credit_1cpu = calculate_unused_compute_credit(
        price_usdc=0.022, cost_floor=0.0145, compute_cost=0.002,
        time_limit_min=10, compute_duration_s=120,
    )
    credit_4cpu = calculate_unused_compute_credit(
        price_usdc=0.060, cost_floor=0.0205, compute_cost=0.008,
        time_limit_min=10, compute_duration_s=120,
    )
    assert credit_4cpu > credit_1cpu


def test_unused_compute_credit_no_cost_floor():
    """Legacy jobs without cost_floor → returns 0."""
    credit = calculate_unused_compute_credit(
        price_usdc=0.022, cost_floor=0, compute_cost=0.002,
        time_limit_min=10, compute_duration_s=120,
    )
    assert credit == 0.0


def test_unused_compute_credit_no_compute_cost():
    """Missing compute_cost → returns 0."""
    credit = calculate_unused_compute_credit(
        price_usdc=0.022, cost_floor=0.0145, compute_cost=0,
        time_limit_min=10, compute_duration_s=120,
    )
    assert credit == 0.0


async def test_calculate_price_git_setup_cost():
    """Git mode has higher setup cost than multi_file."""
    from unittest.mock import AsyncMock, MagicMock

    from src.api.pricing import SETUP_COST_BY_MODE, calculate_price

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    quote_git = await calculate_price(db, 1, 1, "git")
    assert quote_git.breakdown["setup_cost"] == pytest.approx(SETUP_COST_BY_MODE["git"])
