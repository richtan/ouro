"""Tests for DB operations (mocked session)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.operations import (
    complete_job,
    fail_job,
    get_available_credit,
    issue_credit,
    log_attribution,
    log_audit,
    log_cost,
    redeem_credits,
)


@pytest.fixture
def db():
    session = AsyncMock()
    return session


async def test_log_cost(db):
    await log_cost(db, "gas", 0.002, {"tx_hash": "0x1"})
    db.add.assert_called_once()
    obj = db.add.call_args[0][0]
    assert obj.cost_type == "gas"
    assert float(obj.amount_usd) == 0.002
    db.commit.assert_awaited_once()


async def test_issue_credit_lowercases_address(db):
    await issue_credit(db, "0xABC", 1.5, "refund")
    obj = db.add.call_args[0][0]
    assert obj.wallet_address == "0xabc"


async def test_get_available_credit(db):
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 1.5
    db.execute.return_value = mock_result
    result = await get_available_credit(db, "0xabc")
    assert result == 1.5


async def test_get_available_credit_zero(db):
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    db.execute.return_value = mock_result
    result = await get_available_credit(db, "0xabc")
    assert result == 0.0


async def test_log_audit_creates_entry(db):
    await log_audit(db, "payment_received", wallet_address="0xabc", amount_usdc=0.05)
    obj = db.add.call_args[0][0]
    assert obj.event_type == "payment_received"
    db.commit.assert_awaited_once()


async def test_log_audit_converts_string_uuid(db):
    job_id = str(uuid.uuid4())
    await log_audit(db, "job_completed", job_id=job_id)
    obj = db.add.call_args[0][0]
    assert obj.job_id == uuid.UUID(job_id)


async def test_log_attribution(db):
    await log_attribution(db, "0xtx", ["ouro", "morpho"], gas_used=50000)
    obj = db.add.call_args[0][0]
    assert obj.tx_hash == "0xtx"
    assert obj.codes == ["ouro", "morpho"]
    db.commit.assert_awaited_once()


async def test_issue_credit_stores_reason(db):
    await issue_credit(db, "0xabc", 2.0, "job_failed:123")
    obj = db.add.call_args[0][0]
    assert obj.reason == "job_failed:123"
    assert float(obj.amount_usdc) == 2.0


async def test_log_cost_with_none_detail(db):
    await log_cost(db, "gas", 0.001, None)
    obj = db.add.call_args[0][0]
    assert obj.detail is None
    assert obj.cost_type == "gas"


# --- complete_job ---


class _FakeBegin:
    """Async context manager that mimics db.begin() (no-op for tests)."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        pass


async def test_complete_job_not_found():
    """Job not found in DB → raises ValueError."""
    db = AsyncMock()
    db.begin = MagicMock(return_value=_FakeBegin())
    db.get.return_value = None

    with pytest.raises(ValueError, match="not found"):
        await complete_job(db, "nonexistent-id", "0xtx", b"\x00", 0.001, 0.001, 10.0)


async def test_complete_job_archives():
    """Job exists → inserts into HistoricalData + deletes from ActiveJob."""
    db = AsyncMock()
    db.begin = MagicMock(return_value=_FakeBegin())

    job = MagicMock()
    job.id = uuid.uuid4()
    job.slurm_job_id = 42
    job.submitter_address = "0xabc"
    job.payload = {"script": "echo hi"}
    job.x402_tx_hash = "0xtx"
    job.price_usdc = Decimal("0.05")
    job.submitted_at = None
    db.get.return_value = job

    await complete_job(db, str(job.id), "0xproof", b"\x01\x02", 0.001, 0.001, 15.0)
    db.execute.assert_awaited_once()  # INSERT into historical_data
    db.delete.assert_awaited_once_with(job)


# --- fail_job ---


async def test_fail_job_archives_and_deletes():
    """Failed job → inserts into HistoricalData with status='failed' + deletes from ActiveJob."""
    db = AsyncMock()
    db.begin = MagicMock(return_value=_FakeBegin())

    job = MagicMock()
    job.id = uuid.uuid4()
    job.slurm_job_id = 99
    job.submitter_address = "0xuser"
    job.payload = {"script": "exit 1"}
    job.x402_tx_hash = "0xtx"
    job.price_usdc = Decimal("0.05")
    job.submitted_at = None
    db.get.return_value = job

    await fail_job(db, str(job.id), "script crashed")
    db.execute.assert_awaited_once()  # INSERT into historical_data
    db.delete.assert_awaited_once_with(job)


async def test_fail_job_already_cleaned_up():
    """Job not found → no-op (already cleaned up)."""
    db = AsyncMock()
    db.begin = MagicMock(return_value=_FakeBegin())
    db.get.return_value = None

    await fail_job(db, "nonexistent-id", "irrelevant")
    db.execute.assert_not_awaited()
    db.delete.assert_not_awaited()


# --- redeem_credits ---


async def test_redeem_credits_full():
    """2 credits totaling $3, redeem $3 → both marked redeemed."""
    db = AsyncMock()
    credit1 = MagicMock()
    credit1.amount_usdc = Decimal("1.00")
    credit1.redeemed = False
    credit2 = MagicMock()
    credit2.amount_usdc = Decimal("2.00")
    credit2.redeemed = False

    mock_result = MagicMock()
    mock_result.scalars.return_value = [credit1, credit2]
    db.execute.return_value = mock_result

    await redeem_credits(db, "0xABC", 3.0)
    assert credit1.redeemed is True
    assert credit2.redeemed is True
    db.commit.assert_awaited_once()


async def test_redeem_credits_partial():
    """2 credits ($1 each), redeem $1.50 → both marked (remaining goes negative)."""
    db = AsyncMock()
    credit1 = MagicMock()
    credit1.amount_usdc = Decimal("1.00")
    credit1.redeemed = False
    credit2 = MagicMock()
    credit2.amount_usdc = Decimal("1.00")
    credit2.redeemed = False

    mock_result = MagicMock()
    mock_result.scalars.return_value = [credit1, credit2]
    db.execute.return_value = mock_result

    await redeem_credits(db, "0xABC", 1.50)
    assert credit1.redeemed is True
    assert credit2.redeemed is True  # remaining=0.50, still marks this one
    db.commit.assert_awaited_once()
