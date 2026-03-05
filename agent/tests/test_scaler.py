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
            _make_node("ouro-spot-sm-1", "CLOUD"),
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
    nodes = [_make_node("ouro-spot-sm-1", "CLOUD")]
    name, template = scaler._pick_node_for_cpus(1, nodes)
    assert name == "ouro-spot-sm-1"
    assert template == "ouro-spot-sm-template"


def test_pick_node_medium_cpu(scaler):
    nodes = [
        _make_node("ouro-spot-sm-1", "CLOUD"),
        _make_node("ouro-spot-md-1", "CLOUD", cpus=4),
    ]
    name, template = scaler._pick_node_for_cpus(3, nodes)
    assert name == "ouro-spot-md-1"
    assert template == "ouro-spot-md-template"


def test_pick_node_large_cpu(scaler):
    nodes = [_make_node("ouro-spot-lg-1", "CLOUD", cpus=8)]
    name, template = scaler._pick_node_for_cpus(6, nodes)
    assert name == "ouro-spot-lg-1"
    assert template == "ouro-spot-lg-template"


def test_pick_node_no_candidates(scaler):
    nodes = [_make_node("ouro-spot-sm-1", "ALLOCATED")]
    name, template = scaler._pick_node_for_cpus(1, nodes)
    assert name is None
    assert template is None


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
