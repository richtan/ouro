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


async def test_mark_failed_platform_error_issues_credit(make_active_job, mock_session_maker, event_bus):
    """_mark_failed issues credit for platform_error (stage 2 = Slurm submission failure)."""
    job = make_active_job(submitter_address="0xuser", price_usdc=Decimal("0.05"))
    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock) as mock_credit,
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        await _mark_failed(mock_session_maker, event_bus, job, "slurm submit error", failure_stage=2, compute_duration_s=7.3)
        mock_fail.assert_awaited_once()
        assert mock_fail.call_args.kwargs["fault"] == "platform_error"
        assert mock_fail.call_args.kwargs["compute_duration_s"] == pytest.approx(7.3)
        mock_credit.assert_awaited_once()
        assert mock_credit.call_args.kwargs["wallet_address"] == "0xuser"
        assert mock_credit.call_args.kwargs["amount_usdc"] == pytest.approx(0.05)


async def test_mark_failed_user_error_no_credit(make_active_job, mock_session_maker, event_bus):
    """_mark_failed does NOT issue credit for user_error (stage 3, Slurm FAILED)."""
    job = make_active_job(submitter_address="0xuser", price_usdc=Decimal("0.05"))
    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock) as mock_credit,
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        await _mark_failed(
            mock_session_maker, event_bus, job, "exit code 1",
            failure_stage=3, compute_duration_s=5.0,
            exit_code=1, slurm_state="FAILED",
        )
        mock_fail.assert_awaited_once()
        assert mock_fail.call_args.kwargs["fault"] == "user_error"
        assert mock_fail.call_args.kwargs.get("failure_stage") == 3
        mock_credit.assert_not_awaited()


async def test_mark_failed_with_failure_stage(make_active_job, mock_session_maker, event_bus):
    """_mark_failed passes failure_stage and compute_duration_s through to fail_job."""
    job = make_active_job(submitter_address="0xuser", price_usdc=Decimal("0.05"))
    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock),
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        # Stage 2 = platform_error, so credit will be issued
        await _mark_failed(mock_session_maker, event_bus, job, "slurm error", failure_stage=2, compute_duration_s=5.0)
        mock_fail.assert_awaited_once()
        assert mock_fail.call_args.kwargs.get("failure_stage") == 2
        assert mock_fail.call_args.kwargs.get("compute_duration_s") == pytest.approx(5.0)


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
    running_job.submitter_address = "0xuser"
    running_job.price_usdc = Decimal("0.05")
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

    with (
        patch("src.agent.processor.fail_job", new_callable=AsyncMock) as mock_fail,
        patch("src.agent.processor.issue_credit", new_callable=AsyncMock),
        patch("src.agent.processor.log_audit", new_callable=AsyncMock),
    ):
        await recover_stuck_jobs(maker, event_bus)
        mock_fail.assert_awaited_once_with(session, str(running_job.id), "recovered_on_startup", failure_stage=3, fault="platform_error")

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


# --- EventBus logging ---


def test_event_bus_emit_logs(event_bus, caplog):
    """EventBus.emit() should also log via Python logger."""
    import logging
    with caplog.at_level(logging.INFO, logger="src.agent.event_bus"):
        event_bus.emit("job", "Job abc123 completed")
    assert any("Job abc123 completed" in record.message for record in caplog.records)
