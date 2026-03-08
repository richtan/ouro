"""Shared fixtures for Ouro agent tests."""

from __future__ import annotations

import os

# Set dummy key before any imports that trigger PydanticAI Agent creation
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.event_bus import EventBus
from src.db.models import ActiveJob


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def mock_chain_client():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_slurm_client():
    client = AsyncMock()
    client.submit_job.return_value = 42
    client.get_job_status.return_value = {"state": "COMPLETED", "exit_code": 0, "reason": ""}
    client.get_job_output.return_value = {"output": "Hello World", "error_output": ""}
    client.create_workspace.return_value = "/ouro-jobs/workspaces/test-workspace"
    client.delete_workspace.return_value = True
    client.cancel_job.return_value = True
    client.get_cluster_info.return_value = {
        "total_nodes": 2,
        "idle_nodes": 2,
        "allocated_nodes": 0,
        "total_cpus": 4,
        "available_cpus": 4,
        "nodes_detail": [
            {"name": "ouro-worker-1", "state": ["IDLE"], "cpus": 2, "free_cpus": 2},
            {"name": "ouro-worker-2", "state": ["IDLE"], "cpus": 2, "free_cpus": 2},
        ],
        "status": "healthy",
    }
    return client


@pytest.fixture
def make_active_job():
    def _factory(**overrides):
        defaults = {
            "id": uuid.uuid4(),
            "status": "pending",
            "retry_count": 0,
            "price_usdc": Decimal("0.05"),
            "submitter_address": "0x1234abcd",
            "payload": {"workspace_path": "/ouro-jobs/workspaces/test", "entrypoint": "job.sh", "cpus": 1, "time_limit_min": 1},
            "slurm_job_id": None,
            "x402_tx_hash": None,
            "submitted_at": None,
            "updated_at": None,
        }
        defaults.update(overrides)
        job = MagicMock(spec=ActiveJob)
        for k, v in defaults.items():
            setattr(job, k, v)
        return job

    return _factory
