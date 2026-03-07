"""Tests for the oracle fast path."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.oracle import (
    OracleDeps,
    _ensure_capacity,
    poll_slurm_status_impl,
    process_job_fast,
    resolve_image_if_needed,
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
            docker_image=None,
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
    mock_slurm_client.get_job_output.return_value = {
        "output": "", "error_output": "segfault", "output_hash": "",
    }
    deps = make_deps()
    result = await poll_slurm_status_impl(deps, slurm_job_id=42)
    assert result.startswith("FAILED:")
    assert "exit_code=1" in result
    assert deps.captured_error == "segfault"
    mock_slurm_client.get_job_output.assert_awaited()


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


# --- Dockerfile integration (resolve_image_if_needed) ---


async def test_validate_with_dockerfile_no_entrypoint(make_deps):
    """When dockerfile_content is set, entrypoint is not required (comes from Dockerfile)."""
    deps = make_deps(
        entrypoint="",
        dockerfile_content='FROM base\nENTRYPOINT ["bash", "job.sh"]',
    )
    result = await validate_request_impl(deps)
    assert result.startswith("VALID")


async def test_resolve_image_prebuilt(make_deps):
    """Prebuilt alias with no RUN → use Docker image directly, no build needed."""
    deps = make_deps(
        dockerfile_content='FROM base\nENTRYPOINT ["bash", "job.sh"]',
    )
    await resolve_image_if_needed(deps)
    assert deps.docker_image == "ubuntu:22.04"
    assert deps.dockerfile_content is None  # cleared — no build
    assert deps.entrypoint_cmd == ["bash", "job.sh"]


async def test_resolve_image_needs_build(make_deps):
    """Prebuilt alias with RUN → docker_image is None, dockerfile_content preserved."""
    deps = make_deps(
        dockerfile_content='FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]',
    )
    await resolve_image_if_needed(deps)
    assert deps.docker_image is None  # worker will docker build
    assert deps.dockerfile_content is not None
    assert deps.entrypoint_cmd == ["python", "main.py"]


async def test_resolve_image_external_no_build(make_deps):
    """FROM ruby:latest with no RUN → docker_image set, no build needed."""
    deps = make_deps(
        dockerfile_content='FROM ruby:latest\nENTRYPOINT ["ruby", "hello.rb"]',
    )
    await resolve_image_if_needed(deps)
    assert deps.docker_image == "ruby:latest"
    assert deps.dockerfile_content is None  # cleared — no build


async def test_resolve_image_complex_needs_build(make_deps):
    """FROM + RUN → docker_image is None, dockerfile_content preserved."""
    deps = make_deps(
        dockerfile_content="FROM python:3.12\nRUN pip install pandas\nCMD python",
    )
    await resolve_image_if_needed(deps)
    assert deps.docker_image is None
    assert deps.dockerfile_content is not None


async def test_fast_path_with_dockerfile_prebuilt(make_deps, mock_slurm_client, mock_chain_client):
    """Full fast path with prebuilt Dockerfile — no build, uses docker_image."""
    deps = make_deps(
        entrypoint="",
        dockerfile_content='FROM base\nENTRYPOINT ["bash", "job.sh"]',
    )
    result = await process_job_fast(deps)
    assert result.status == "completed"
    assert result.proof_tx == "0xabc123"
    # submit_job should have been called with docker_image and entrypoint_cmd
    call_kwargs = mock_slurm_client.submit_job.call_args.kwargs
    assert call_kwargs["docker_image"] == "ubuntu:22.04"
    assert call_kwargs["entrypoint_cmd"] == ["bash", "job.sh"]


async def test_fast_path_resolve_failure_fails_job(make_deps, mock_slurm_client, mock_chain_client):
    """Parse failure should fail the job."""
    deps = make_deps(
        entrypoint="",
        dockerfile_content='INVALID DOCKERFILE',  # no FROM
    )
    result = await process_job_fast(deps)
    assert result.status == "failed"
    mock_slurm_client.submit_job.assert_not_awaited()


async def test_no_dockerfile_legacy_path(make_deps):
    """Without dockerfile_content, resolve_image_if_needed is a no-op."""
    deps = make_deps(dockerfile_content=None)
    await resolve_image_if_needed(deps)
    assert deps.docker_image is None
    assert deps.entrypoint_cmd is None


# --- _ensure_capacity ---


async def test_ensure_capacity_sufficient(make_deps, mock_slurm_client):
    """When cluster has enough CPUs, _ensure_capacity is a no-op."""
    deps = make_deps(cpus=2)
    await _ensure_capacity(deps)
    mock_slurm_client.get_cluster_info.assert_awaited_once()


async def test_ensure_capacity_scaling_disabled(make_deps, mock_slurm_client, monkeypatch):
    """When scaling is disabled and no node has enough CPUs, raise RuntimeError."""
    monkeypatch.setattr("src.agent.oracle.settings.AUTO_SCALING_ENABLED", False)
    deps = make_deps(cpus=4)
    with pytest.raises(RuntimeError, match="No node has 4 CPUs"):
        await _ensure_capacity(deps)


async def test_ensure_capacity_boots_spot(make_deps, mock_slurm_client, monkeypatch):
    """When scaling enabled, boots a spot node and waits for IDLE."""
    monkeypatch.setattr("src.agent.oracle.settings.AUTO_SCALING_ENABLED", True)
    from src.slurm.scaler import ScalingEvent

    # Mock the scaler methods
    mock_boot = AsyncMock(return_value=ScalingEvent("scale_out", "ouro-spot-md-1", "pending"))
    monkeypatch.setattr("src.agent.oracle._scaler._boot_spot_instance", mock_boot)

    # First get_cluster_info: no 4-CPU node. Second: spot node is IDLE.
    mock_slurm_client.get_cluster_info.side_effect = [
        {
            "nodes_detail": [
                {"name": "ouro-worker-1", "state": ["IDLE"], "cpus": 2, "free_cpus": 2},
            ],
        },
        {
            "nodes_detail": [
                {"name": "ouro-worker-1", "state": ["IDLE"], "cpus": 2, "free_cpus": 2},
                {"name": "ouro-spot-md-1", "state": ["IDLE"], "cpus": 4, "free_cpus": 4},
            ],
        },
    ]

    deps = make_deps(cpus=4)
    await _ensure_capacity(deps)
    mock_boot.assert_awaited_once()


# --- poll_slurm_status_impl: status tracking ---


async def test_poll_marks_running_on_transition(make_deps, mock_slurm_client):
    """Poll should update DB status to 'running' when Slurm state becomes RUNNING."""
    mock_slurm_client.get_job_status.side_effect = [
        {"state": "PENDING", "exit_code": 0, "reason": ""},
        {"state": "RUNNING", "exit_code": 0, "reason": ""},
        {"state": "COMPLETED", "exit_code": 0, "reason": ""},
    ]
    deps = make_deps()
    result = await poll_slurm_status_impl(deps, slurm_job_id=42)
    assert result.startswith("COMPLETED:")
    # DB should have been updated to "running" then committed
    deps.db.execute.assert_awaited()
    deps.db.commit.assert_awaited()


# --- poll_slurm_status_impl: PENDING detection ---


async def test_poll_cancels_stuck_pending(make_deps, mock_slurm_client):
    """After 6 PENDING polls with ReqNodeNotAvail, should cancel and fail."""
    mock_slurm_client.get_job_status.return_value = {
        "state": "PENDING",
        "exit_code": 0,
        "reason": "ReqNodeNotAvail",
    }
    deps = make_deps()
    result = await poll_slurm_status_impl(deps, slurm_job_id=42)
    assert result.startswith("FAILED:")
    assert "ReqNodeNotAvail" in result
    mock_slurm_client.cancel_job.assert_awaited_once_with(42)


# --- submit_to_slurm_impl: status stays processing ---


async def test_submit_keeps_processing_status(make_deps, mock_slurm_client):
    """submit_to_slurm_impl should NOT set status='running' — only store slurm_job_id."""
    deps = make_deps()
    result = await submit_to_slurm_impl(deps)
    assert "SUBMITTED" in result
    # Check the DB update call did NOT include status="running"
    call_args = deps.db.execute.call_args
    # The update statement values should only have slurm_job_id, not status
    update_stmt = call_args[0][0]
    # Verify by checking the compiled parameters
    compiled = update_stmt.compile()
    assert "status" not in compiled.params
