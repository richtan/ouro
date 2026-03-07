"""Tests for the auto-scaler module."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.slurm.scaler import AutoScaler, ScalingEvent


def _make_cluster_info(
    nodes: list[dict] | None = None,
    available_cpus: int = 0,
) -> dict:
    """Build a cluster_info dict for testing."""
    nodes = nodes or []
    return {
        "total_nodes": len(nodes),
        "available_cpus": available_cpus,
        "nodes_detail": nodes,
    }


def _make_node(name: str, state: str, cpus: int = 2) -> dict:
    return {"name": name, "state": [state], "cpus": cpus, "free_cpus": 0}


@pytest.fixture
def scaler():
    return AutoScaler()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute.return_value = mock_result
    return db


# --- No action when no pending jobs ---


async def test_no_action_when_no_pending_jobs(scaler, mock_db):
    cluster = _make_cluster_info(
        nodes=[_make_node("ouro-worker-1", "IDLE")],
        available_cpus=2,
    )
    event = await scaler.evaluate_and_act(cluster, mock_db)
    assert event is None


# --- No action during cooldown ---


async def test_cooldown_prevents_action(scaler, mock_db):
    scaler.last_scale_time = datetime.now(timezone.utc)
    cluster = _make_cluster_info()
    event = await scaler.evaluate_and_act(cluster, mock_db)
    assert event is None


# --- Scale out when pending jobs exceed capacity ---


async def test_scale_out_when_no_capacity(scaler):
    db = AsyncMock()
    # Simulate 1 pending job needing 2 CPUs
    mock_result = MagicMock()
    mock_result.all.return_value = [
        MagicMock(id="job-1", payload={"cpus": 2}),
    ]
    db.execute.return_value = mock_result

    cluster = _make_cluster_info(
        nodes=[
            _make_node("ouro-worker-1", "ALLOCATED"),
        ],
        available_cpus=0,
    )

    with patch.object(scaler, "_boot_spot_instance", new_callable=AsyncMock) as mock_boot:
        mock_boot.return_value = ScalingEvent("scale_out", "ouro-spot-sm-1", "test")
        event = await scaler.evaluate_and_act(cluster, db)

    assert event is not None
    assert event.action == "scale_out"
    assert event.node_name == "ouro-spot-sm-1"


# --- Scale down idle spot nodes ---


async def test_scale_down_idle_spot(scaler, mock_db):
    cluster = _make_cluster_info(
        nodes=[
            _make_node("ouro-worker-1", "IDLE"),
            _make_node("ouro-spot-sm-1", "IDLE"),
        ],
        available_cpus=4,
    )

    # Pre-set idle tracking so the node is past the drain threshold
    scaler._idle_since["ouro-spot-sm-1"] = datetime.now(timezone.utc) - timedelta(minutes=10)

    with patch.object(scaler, "_terminate_spot_instance", new_callable=AsyncMock) as mock_term:
        mock_term.return_value = ScalingEvent("scale_down", "ouro-spot-sm-1", "idle")
        event = await scaler.evaluate_and_act(cluster, mock_db)

    assert event is not None
    assert event.action == "scale_down"
    assert event.node_name == "ouro-spot-sm-1"


# --- Idle tracking cleanup ---


async def test_idle_tracking_cleanup(scaler, mock_db):
    """Nodes that are no longer idle get removed from tracking."""
    scaler._idle_since["ouro-spot-sm-1"] = datetime.now(timezone.utc) - timedelta(minutes=1)

    cluster = _make_cluster_info(
        nodes=[_make_node("ouro-spot-sm-1", "ALLOCATED")],
        available_cpus=0,
    )

    await scaler.evaluate_and_act(cluster, mock_db)
    assert "ouro-spot-sm-1" not in scaler._idle_since


# --- Pick correct tier for CPU request ---


def test_pick_node_small_cpu(scaler):
    """FUTURE nodes are invisible; pick first unprovisioned sm node."""
    nodes = [_make_node("ouro-worker-1", "IDLE")]  # Only static nodes visible
    name, template = scaler._pick_node_for_cpus(1, nodes)
    assert name == "ouro-spot-sm-1"
    assert template == "ouro-spot-sm-template"


def test_pick_node_medium_cpu(scaler):
    """3 CPUs need a medium node; all sm nodes are too small."""
    nodes = [_make_node("ouro-worker-1", "IDLE")]
    name, template = scaler._pick_node_for_cpus(3, nodes)
    assert name == "ouro-spot-md-1"
    assert template == "ouro-spot-md-template"


def test_pick_node_large_cpu(scaler):
    """6 CPUs need a large node."""
    nodes = [_make_node("ouro-worker-1", "IDLE")]
    name, template = scaler._pick_node_for_cpus(6, nodes)
    assert name == "ouro-spot-lg-1"
    assert template == "ouro-spot-lg-template"


def test_pick_node_no_candidates(scaler):
    """When CPU request exceeds all tier capacities, return None."""
    nodes = [_make_node("ouro-worker-1", "IDLE")]
    name, template = scaler._pick_node_for_cpus(16, nodes)  # No tier has 16 CPUs
    assert name is None
    assert template is None


def test_pick_node_skips_visible(scaler):
    """When all sm nodes are already visible, falls through to md tier."""
    nodes = [_make_node(f"ouro-spot-sm-{i}", "ALLOCATED") for i in range(1, 11)]
    name, template = scaler._pick_node_for_cpus(1, nodes)
    assert name == "ouro-spot-md-1"
    assert template == "ouro-spot-md-template"


# --- Max spot cap ---


async def test_max_spot_cap_prevents_scale_out(scaler):
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [MagicMock(id="job-1", payload={"cpus": 1})]
    db.execute.return_value = mock_result

    # All 18 spot nodes active
    nodes = [_make_node(f"ouro-spot-sm-{i}", "ALLOCATED") for i in range(1, 19)]
    cluster = _make_cluster_info(nodes=nodes, available_cpus=0)

    event = await scaler.evaluate_and_act(cluster, db)
    assert event is None


# --- Stale booting nodes get cleaned up ---


async def test_stale_booting_cleanup(scaler, mock_db):
    scaler._booting["ouro-spot-sm-1"] = datetime.now(timezone.utc) - timedelta(minutes=5)

    cluster = _make_cluster_info(
        nodes=[_make_node("ouro-spot-sm-1", "CLOUD")],
        available_cpus=2,
    )

    await scaler.evaluate_and_act(cluster, mock_db)
    assert "ouro-spot-sm-1" not in scaler._booting


# --- cpus_for_node ---


def test_cpus_for_node(scaler):
    assert scaler._cpus_for_node("ouro-spot-sm-1") == 2
    assert scaler._cpus_for_node("ouro-spot-md-3") == 4
    assert scaler._cpus_for_node("ouro-spot-lg-1") == 8
    assert scaler._cpus_for_node("ouro-worker-1") == 2  # default


# --- 409 "already exists" treated as success ---


def _mock_compute_v1():
    """Create a mock google.cloud.compute_v1 module for tests."""
    mock_mod = MagicMock()
    mock_mod.Instance.return_value = MagicMock()
    mock_mod.InsertInstanceRequest.return_value = MagicMock()
    return mock_mod


async def test_boot_409_already_exists_treated_as_success(scaler):
    """When GCP returns 409 'already exists', treat it as a successful boot."""
    mock_compute = _mock_compute_v1()
    with (
        patch("src.slurm.scaler._get_gcp_client") as mock_client_fn,
        patch.dict("sys.modules", {"google.cloud.compute_v1": mock_compute, "google.cloud": MagicMock(compute_v1=mock_compute)}),
    ):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_op = MagicMock()
        mock_op.result.side_effect = Exception(
            "409 POST ... The resource "
            "'projects/ouro-hpc-2026/zones/us-central1-a/instances/ouro-spot-md-1' "
            "already exists"
        )
        mock_client.insert.return_value = mock_op

        event = await scaler._boot_spot_instance(
            "ouro-spot-md-1", "ouro-spot-md-template"
        )

    assert event is not None
    assert event.action == "scale_out"
    assert event.node_name == "ouro-spot-md-1"
    assert "already exists" in event.reason


async def test_boot_other_error_returns_boot_failed(scaler):
    """Non-409 errors should still return boot_failed."""
    mock_compute = _mock_compute_v1()
    with (
        patch("src.slurm.scaler._get_gcp_client") as mock_client_fn,
        patch.dict("sys.modules", {"google.cloud.compute_v1": mock_compute, "google.cloud": MagicMock(compute_v1=mock_compute)}),
    ):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_op = MagicMock()
        mock_op.result.side_effect = Exception("quota exceeded")
        mock_client.insert.return_value = mock_op

        event = await scaler._boot_spot_instance(
            "ouro-spot-sm-1", "ouro-spot-sm-template"
        )

    assert event is not None
    assert event.action == "boot_failed"
    assert "quota exceeded" in event.reason
