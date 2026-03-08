"""Tests for the failure classifier."""

from __future__ import annotations

import pytest

from src.agent.classifier import classify_failure


# --- Stage 1: validation / capacity ---


def test_stage1_validation_error_is_user_error():
    assert classify_failure(1, "INVALID: entrypoint required") == "user_error"


def test_stage1_invalid_cpus_is_user_error():
    assert classify_failure(1, "INVALID: cpus must be between 1 and 8") == "user_error"


def test_stage1_image_resolution_is_user_error():
    assert classify_failure(1, "Image resolution failed: invalid Dockerfile") == "user_error"


def test_stage1_capacity_failure_is_platform_error():
    assert classify_failure(1, "Capacity check failed: No node has 4 CPUs") == "platform_error"


def test_stage1_scaling_failure_is_platform_error():
    assert classify_failure(1, "Scaling out failed") == "platform_error"


# --- Stage 2: Slurm submission ---


def test_stage2_always_platform_error():
    assert classify_failure(2, "Slurm submission error: cluster down") == "platform_error"


def test_stage2_any_reason_platform_error():
    assert classify_failure(2, "connection refused") == "platform_error"


# --- Stage 3: Slurm execution ---


def test_stage3_failed_is_user_error():
    """Slurm FAILED = user code exited non-zero."""
    assert classify_failure(3, "exit code 1", exit_code=1, slurm_state="FAILED") == "user_error"


def test_stage3_failed_exit_143_still_user_error():
    """Self-SIGTERM (exit 143) produces Slurm state FAILED, not CANCELLED."""
    assert classify_failure(3, "exit code 143", exit_code=143, slurm_state="FAILED") == "user_error"


def test_stage3_timeout_is_user_error():
    """User code exceeded requested time_limit."""
    assert classify_failure(3, "time limit", exit_code=0, slurm_state="TIMEOUT") == "user_error"


def test_stage3_cancelled_is_platform_error():
    """Users can't cancel from inside Docker (--network none)."""
    assert classify_failure(3, "cancelled", exit_code=0, slurm_state="CANCELLED") == "platform_error"


def test_stage3_node_fail_is_platform_error():
    """Infrastructure node crashed."""
    assert classify_failure(3, "node failure", exit_code=0, slurm_state="NODE_FAIL") == "platform_error"


def test_stage3_pending_stuck_is_platform_error():
    """Stuck PENDING = no suitable node."""
    assert classify_failure(3, "ReqNodeNotAvail", slurm_state="PENDING") == "platform_error"


def test_stage3_no_slurm_state_defaults_platform():
    """If slurm_state is missing, benefit of the doubt."""
    assert classify_failure(3, "unknown error") == "platform_error"


# --- asyncio.TimeoutError / unhandled exceptions ---


def test_no_stage_timeout_platform_error():
    """asyncio.TimeoutError in processor → platform_error."""
    assert classify_failure(3, "timeout after 900s") == "platform_error"


def test_no_stage_unknown_defaults_platform():
    """Unknown failure → benefit of the doubt."""
    assert classify_failure(None, "something unexpected") == "platform_error"


# --- Poll timeout ---


def test_poll_timeout_platform_error():
    assert classify_failure(3, "TIMEOUT: polling exceeded 5 minutes") == "platform_error"
