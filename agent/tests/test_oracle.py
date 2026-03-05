"""Tests for the oracle fast path."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.oracle import (
    OracleDeps,
    build_image_if_needed,
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
            workspace_path="/ouro-jobs/workspaces/test",
            entrypoint="job.sh",
            image="base",
            partition="default",
            cpus=1,
            time_limit_min=1,
            client_builder_code=None,
            slurm_client=mock_slurm_client,
            chain_client=mock_chain_client,
            db=AsyncMock(),
            event_bus=event_bus,
            dockerfile_content=None,
            sif_path=None,
            entrypoint_cmd=None,
        )
        defaults.update(overrides)
        return OracleDeps(**defaults)

    return _factory


# --- validate_request_impl ---


async def test_validate_valid(make_deps):
    result = await validate_request_impl(make_deps())
    assert result.startswith("VALID")


async def test_validate_empty_entrypoint(make_deps):
    result = await validate_request_impl(make_deps(entrypoint=""))
    assert "INVALID" in result
    assert "entrypoint" in result


async def test_validate_empty_workspace_path(make_deps):
    result = await validate_request_impl(make_deps(workspace_path=""))
    assert "INVALID" in result
    assert "workspace_path" in result


async def test_validate_cpus_too_high(make_deps):
    result = await validate_request_impl(make_deps(cpus=9))
    assert "INVALID" in result
    assert "cpus" in result


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
    # Workspace should always be cleaned up
    mock_slurm_client.delete_workspace.assert_awaited_once()


async def test_fast_path_validation_fail(make_deps, mock_slurm_client):
    deps = make_deps(entrypoint="")
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


async def test_validate_cpus_zero(make_deps):
    result = await validate_request_impl(make_deps(cpus=0))
    assert "INVALID" in result
    assert "cpus" in result


async def test_validate_cpus_boundary_valid(make_deps):
    result1 = await validate_request_impl(make_deps(cpus=1))
    assert result1.startswith("VALID")
    result8 = await validate_request_impl(make_deps(cpus=8))
    assert result8.startswith("VALID")


async def test_validate_time_zero(make_deps):
    result = await validate_request_impl(make_deps(time_limit_min=0))
    assert "INVALID" in result
    assert "time_limit_min" in result


async def test_validate_time_boundary_valid(make_deps):
    result1 = await validate_request_impl(make_deps(time_limit_min=1))
    assert result1.startswith("VALID")
    result60 = await validate_request_impl(make_deps(time_limit_min=60))
    assert result60.startswith("VALID")


async def test_validate_missing_entrypoint(make_deps):
    result = await validate_request_impl(make_deps(
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="",
    ))
    assert "INVALID" in result
    assert "entrypoint" in result


async def test_validate_missing_workspace(make_deps):
    result = await validate_request_impl(make_deps(
        workspace_path="",
        entrypoint="main.py",
    ))
    assert "INVALID" in result
    assert "workspace_path" in result


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


# --- Dockerfile integration ---


async def test_validate_with_dockerfile_no_entrypoint(make_deps):
    """When dockerfile_content is set, entrypoint is not required (comes from Dockerfile)."""
    deps = make_deps(
        entrypoint="",
        dockerfile_content='FROM base\nENTRYPOINT ["bash", "job.sh"]',
    )
    result = await validate_request_impl(deps)
    assert result.startswith("VALID")


async def test_build_image_prebuilt(make_deps, mock_slurm_client):
    """Prebuilt alias with no RUN → use prebuilt .sif directly, no build call."""
    deps = make_deps(
        dockerfile_content='FROM base\nENTRYPOINT ["bash", "job.sh"]',
    )
    await build_image_if_needed(deps)
    assert deps.sif_path is not None
    assert "base.sif" in deps.sif_path
    assert deps.entrypoint_cmd == ["bash", "job.sh"]
    mock_slurm_client.build_image.assert_not_awaited()


async def test_build_image_needs_build(make_deps, mock_slurm_client):
    """Prebuilt alias with RUN → calls build_image, uses returned sif_path."""
    mock_slurm_client.build_image.return_value = {
        "sif_path": "/ouro-jobs/images/custom/abc123.sif",
        "cached": False,
        "build_time_s": 5.0,
    }
    deps = make_deps(
        dockerfile_content='FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]',
    )
    await build_image_if_needed(deps)
    assert deps.sif_path == "/ouro-jobs/images/custom/abc123.sif"
    assert deps.entrypoint_cmd == ["python", "main.py"]
    mock_slurm_client.build_image.assert_awaited_once()


async def test_build_image_failure(make_deps, mock_slurm_client):
    """Build failure should propagate as exception."""
    mock_slurm_client.build_image.side_effect = RuntimeError("build failed")
    deps = make_deps(
        dockerfile_content='FROM python312\nRUN pip install broken\nENTRYPOINT ["python", "main.py"]',
    )
    with pytest.raises(RuntimeError, match="build failed"):
        await build_image_if_needed(deps)


async def test_fast_path_with_dockerfile_prebuilt(make_deps, mock_slurm_client, mock_chain_client):
    """Full fast path with prebuilt Dockerfile — no build, uses sif_path."""
    deps = make_deps(
        entrypoint="",
        dockerfile_content='FROM base\nENTRYPOINT ["bash", "job.sh"]',
    )
    result = await process_job_fast(deps)
    assert result.status == "completed"
    assert result.proof_tx == "0xabc123"
    # submit_job should have been called with sif_path and entrypoint_cmd
    call_kwargs = mock_slurm_client.submit_job.call_args.kwargs
    assert call_kwargs["sif_path"] is not None
    assert call_kwargs["entrypoint_cmd"] == ["bash", "job.sh"]
    mock_slurm_client.build_image.assert_not_awaited()


async def test_fast_path_build_failure_fails_job(make_deps, mock_slurm_client, mock_chain_client):
    """Build failure should fail the job."""
    mock_slurm_client.build_image.side_effect = RuntimeError("build failed")
    deps = make_deps(
        entrypoint="",
        dockerfile_content='FROM python312\nRUN pip install broken\nENTRYPOINT ["python", "main.py"]',
    )
    result = await process_job_fast(deps)
    assert result.status == "failed"
    mock_slurm_client.submit_job.assert_not_awaited()


async def test_no_dockerfile_legacy_path(make_deps, mock_slurm_client):
    """Without dockerfile_content, build_image_if_needed is a no-op."""
    deps = make_deps(dockerfile_content=None)
    await build_image_if_needed(deps)
    assert deps.sif_path is None
    assert deps.entrypoint_cmd is None
    mock_slurm_client.build_image.assert_not_awaited()
