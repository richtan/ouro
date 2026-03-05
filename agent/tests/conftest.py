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
    client.submit_proof.return_value = MagicMock(
        tx_hash="0xabc123",
        gas_cost_usd=0.001,
        gas_cost_wei=100000,
        codes=["ouro"],
    )
    return client


@pytest.fixture
def mock_slurm_client():
    client = AsyncMock()
    client.submit_job.return_value = 42
    client.get_job_status.return_value = {"state": "COMPLETED", "exit_code": 0}
    client.get_job_output.return_value = "Hello World"
    client.create_workspace.return_value = "/ouro-jobs/workspaces/test-workspace"
    client.delete_workspace.return_value = True
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
            "payload": {"script": "echo hello", "nodes": 1, "time_limit_min": 1},
            "slurm_job_id": None,
            "x402_tx_hash": None,
            "client_builder_code": None,
            "submitted_at": None,
            "updated_at": None,
        }
        defaults.update(overrides)
        job = MagicMock(spec=ActiveJob)
        for k, v in defaults.items():
            setattr(job, k, v)
        return job

    return _factory
