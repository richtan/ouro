"""Tests for the oracle fast path."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.oracle import (
    OracleDeps,
    poll_slurm_status_impl,
    process_job_fast,
    submit_onchain_proof_impl,
    submit_to_slurm_impl,
    validate_request_impl,
)


@pytest.fixture
def make_deps(event_bus, mock_slurm_client, mock_chain_client):
    def _factory(**overrides):
        defaults = dict(
            job_id="test-job-1",
            script="echo hello",
            partition="default",
            nodes=1,
            time_limit_min=1,
            client_builder_code=None,
            slurm_client=mock_slurm_client,
            chain_client=mock_chain_client,
            db=AsyncMock(),
            event_bus=event_bus,
        )
        defaults.update(overrides)
        return OracleDeps(**defaults)

    return _factory


# --- validate_request_impl ---


async def test_validate_valid(make_deps):
    result = await validate_request_impl(make_deps())
    assert result.startswith("VALID")


async def test_validate_empty_script(make_deps):
    result = await validate_request_impl(make_deps(script=""))
    assert "INVALID" in result
    assert "empty" in result


async def test_validate_nodes_too_high(make_deps):
    result = await validate_request_impl(make_deps(nodes=17))
    assert "INVALID" in result
    assert "nodes" in result


async def test_validate_time_too_high(make_deps):
    result = await validate_request_impl(make_deps(time_limit_min=61))
    assert "INVALID" in result
    assert "time_limit_min" in result


# --- process_job_fast ---


async def test_fast_path_happy(make_deps, mock_slurm_client, mock_chain_client):
    deps = make_deps()
    result = await process_job_fast(deps)
    assert result.status == "completed"
    assert result.proof_tx == "0xabc123"
    assert result.output_hash is not None
    mock_slurm_client.submit_job.assert_awaited_once()
    mock_chain_client.submit_proof.assert_awaited_once()


async def test_fast_path_validation_fail(make_deps, mock_slurm_client):
    deps = make_deps(script="")
    result = await process_job_fast(deps)
    assert result.status == "failed"
    mock_slurm_client.submit_job.assert_not_awaited()


async def test_fast_path_slurm_error(make_deps, mock_slurm_client, mock_chain_client):
    mock_slurm_client.submit_job.side_effect = RuntimeError("cluster down")
    deps = make_deps()
    result = await process_job_fast(deps)
    assert result.status == "failed"
    mock_chain_client.submit_proof.assert_not_awaited()


async def test_fast_path_proof_error(make_deps, mock_chain_client):
    mock_chain_client.submit_proof.side_effect = RuntimeError("rpc error")
    deps = make_deps()
    result = await process_job_fast(deps)
    assert result.status == "completed_no_proof"


# --- validate_request_impl boundary cases ---


async def test_validate_nodes_zero(make_deps):
    result = await validate_request_impl(make_deps(nodes=0))
    assert "INVALID" in result
    assert "nodes" in result


async def test_validate_nodes_boundary_valid(make_deps):
    result1 = await validate_request_impl(make_deps(nodes=1))
    assert result1.startswith("VALID")
    result16 = await validate_request_impl(make_deps(nodes=16))
    assert result16.startswith("VALID")


async def test_validate_time_zero(make_deps):
    result = await validate_request_impl(make_deps(time_limit_min=0))
    assert "INVALID" in result
    assert "time_limit_min" in result


async def test_validate_time_boundary_valid(make_deps):
    result1 = await validate_request_impl(make_deps(time_limit_min=1))
    assert result1.startswith("VALID")
    result60 = await validate_request_impl(make_deps(time_limit_min=60))
    assert result60.startswith("VALID")


async def test_validate_whitespace_script(make_deps):
    result = await validate_request_impl(make_deps(script="  \n\t "))
    assert "INVALID" in result
    assert "empty" in result


# --- submit_to_slurm_impl ---


async def test_submit_to_slurm_success(make_deps, mock_slurm_client):
    deps = make_deps()
    result = await submit_to_slurm_impl(deps)
    assert "SUBMITTED" in result
    assert "slurm_job_id=42" in result
    mock_slurm_client.submit_job.assert_awaited_once()


async def test_submit_to_slurm_error(make_deps, mock_slurm_client):
    mock_slurm_client.submit_job.side_effect = RuntimeError("cluster down")
    deps = make_deps()
    result = await submit_to_slurm_impl(deps)
    assert result.startswith("ERROR:")
    assert "cluster down" in result


# --- poll_slurm_status_impl ---


async def test_poll_completed(make_deps, mock_slurm_client):
    deps = make_deps()
    result = await poll_slurm_status_impl(deps, slurm_job_id=42)
    assert result.startswith("COMPLETED:")
    assert deps.captured_output == "Hello World"


async def test_poll_failed_state(make_deps, mock_slurm_client):
    mock_slurm_client.get_job_status.return_value = {"state": "FAILED", "exit_code": 1}
    deps = make_deps()
    result = await poll_slurm_status_impl(deps, slurm_job_id=42)
    assert result.startswith("FAILED:")
    assert "exit_code=1" in result


# --- submit_onchain_proof_impl ---


async def test_submit_proof_success(make_deps, mock_chain_client):
    deps = make_deps()
    # Need a mock db that supports log_cost and log_attribution
    deps.db = AsyncMock()
    result = await submit_onchain_proof_impl(deps, "Hello World")
    assert result.startswith("PROOF_POSTED:")
    assert "tx_hash=0xabc123" in result
    assert deps.captured_gas_cost_usd == 0.001
    mock_chain_client.submit_proof.assert_awaited_once()
