"""Tests for the job processor control flow."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.processor import MAX_RETRIES, _is_transient, _mark_failed, _maybe_retry


# --- _is_transient ---


def test_is_transient_timeout():
    assert _is_transient("TIMEOUT") is True


def test_is_transient_connection():
    assert _is_transient("connection refused") is True


def test_is_transient_unreachable():
    assert _is_transient("host unreachable") is True


def test_is_transient_slurm_error():
    assert _is_transient("slurm_error: node down") is True


def test_is_transient_permanent():
    assert _is_transient("invalid script") is False


def test_is_transient_case_insensitive():
    assert _is_transient("Connection reset by peer") is True


# --- _maybe_retry ---


@pytest.fixture
def mock_session_maker():
    """Returns a session maker whose sessions auto-commit."""
    session = AsyncMock()

    class _CtxMgr:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            pass

    maker = MagicMock()
    maker.return_value = _CtxMgr()
    return maker


async def test_maybe_retry_succeeds(make_active_job, mock_session_maker, event_bus):
    job = make_active_job(retry_count=0)
    result = await _maybe_retry(mock_session_maker, event_bus, job, "connection refused")
    assert result is True


async def test_maybe_retry_at_limit(make_active_job, mock_session_maker, event_bus):
    job = make_active_job(retry_count=MAX_RETRIES)
    result = await _maybe_retry(mock_session_maker, event_bus, job, "connection refused")
    assert result is False


async def test_maybe_retry_permanent(make_active_job, mock_session_maker, event_bus):
    job = make_active_job(retry_count=0)
    result = await _maybe_retry(mock_session_maker, event_bus, job, "invalid script")
    assert result is False


# --- _mark_failed ---


async def test_mark_failed_archives_and_issues_credit(make_active_job, mock_session_maker, event_bus):
    """_mark_failed calls fail_job to archive, then issues credit."""
    job = make_active_job(submitter_address="0xuser", price_usdc=Decimal("0.05"))
    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock) as mock_credit,
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        await _mark_failed(mock_session_maker, event_bus, job, "test failure")
        mock_fail.assert_awaited_once()
        assert mock_fail.call_args[1].get("reason", mock_fail.call_args[0][-1]) == "test failure"
        mock_credit.assert_awaited_once()
        assert mock_credit.call_args.kwargs["wallet_address"] == "0xuser"
        assert mock_credit.call_args.kwargs["amount_usdc"] == pytest.approx(0.05)


async def test_mark_failed_no_submitter(make_active_job, mock_session_maker, event_bus):
    """No submitter_address → skips credit issuance but still archives."""
    job = make_active_job(submitter_address=None, price_usdc=Decimal("0.05"))
    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock) as mock_credit,
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        await _mark_failed(mock_session_maker, event_bus, job, "test failure")
        mock_fail.assert_awaited_once()
        mock_credit.assert_not_awaited()


async def test_mark_failed_zero_price(make_active_job, mock_session_maker, event_bus):
    """price_usdc=0 → skips credit issuance but still archives."""
    job = make_active_job(submitter_address="0xuser", price_usdc=Decimal("0"))
    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock) as mock_credit,
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        await _mark_failed(mock_session_maker, event_bus, job, "test failure")
        mock_fail.assert_awaited_once()
        mock_credit.assert_not_awaited()


async def test_maybe_retry_over_limit(make_active_job, mock_session_maker, event_bus):
    """retry_count > MAX_RETRIES → returns False."""
    job = make_active_job(retry_count=3)
    result = await _maybe_retry(mock_session_maker, event_bus, job, "connection refused")
    assert result is False


# --- recover_stuck_jobs ---


async def test_recover_stuck_processing(event_bus):
    """Processing jobs are reset to pending."""
    from src.agent.processor import recover_stuck_jobs

    session = AsyncMock()
    # First execute: processing → pending, returns 2 IDs
    proc_result = MagicMock()
    proc_result.scalars.return_value.all.return_value = [uuid.uuid4(), uuid.uuid4()]
    # Second execute: running → failed, returns empty
    run_result = MagicMock()
    run_result.scalars.return_value.all.return_value = []

    session.execute.side_effect = [proc_result, run_result]

    class _CtxMgr:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            pass

    maker = MagicMock()
    maker.return_value = _CtxMgr()

    await recover_stuck_jobs(maker, event_bus)
    session.commit.assert_awaited_once()
    messages = [e.message for e in event_bus._history if e.type == "system"]
    assert any("2" in msg and "pending" in msg for msg in messages)


async def test_recover_stuck_running(event_bus):
    """Running jobs are archived via fail_job."""
    from src.agent.processor import recover_stuck_jobs

    session = AsyncMock()
    proc_result = MagicMock()
    proc_result.scalars.return_value.all.return_value = []

    # Running jobs: now returns ActiveJob-like objects via select()
    running_job = MagicMock()
    running_job.id = uuid.uuid4()
    run_result = MagicMock()
    run_result.scalars.return_value.all.return_value = [running_job]

    session.execute.side_effect = [proc_result, run_result]

    class _CtxMgr:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            pass

    maker = MagicMock()
    maker.return_value = _CtxMgr()

    with patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail:
        await recover_stuck_jobs(maker, event_bus)
        mock_fail.assert_awaited_once_with(session, str(running_job.id), "recovered_on_startup")

    messages = [e.message for e in event_bus._history if e.type == "system"]
    assert any("1" in msg and "failed" in msg for msg in messages)


async def test_recover_stuck_nothing(event_bus):
    """No stuck jobs → no events emitted."""
    from src.agent.processor import recover_stuck_jobs

    session = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute.side_effect = [empty_result, empty_result]

    class _CtxMgr:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            pass

    maker = MagicMock()
    maker.return_value = _CtxMgr()

    await recover_stuck_jobs(maker, event_bus)
    system_messages = [e for e in event_bus._history if e.type == "system"]
    assert system_messages == []
