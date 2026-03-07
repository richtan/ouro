"""Tests for EventBus: job_id field, subscribe_job filtering, connection limits."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import pytest

from src.agent.event_bus import MAX_JOB_SSE_CONNECTIONS, EventBus


def test_emit_with_job_id():
    bus = EventBus()
    bus.emit("agent", "test message", job_id="job-123")
    assert len(bus._history) == 1
    assert bus._history[0].job_id == "job-123"
    assert bus._history[0].type == "agent"
    assert bus._history[0].message == "test message"


def test_emit_without_job_id():
    bus = EventBus()
    bus.emit("system", "system message")
    assert len(bus._history) == 1
    assert bus._history[0].job_id is None


@pytest.mark.asyncio
async def test_subscribe_job_only_yields_matching_events():
    bus = EventBus()
    # Pre-populate history with events for different jobs
    bus.emit("agent", "job A event", job_id="job-A")
    bus.emit("agent", "job B event", job_id="job-B")
    bus.emit("system", "no job event")
    bus.emit("agent", "job A event 2", job_id="job-A")

    collected = []

    async def consume():
        async for event in bus.subscribe_job("job-A"):
            collected.append(event)
            if len(collected) >= 3:
                break

    # Start consumer
    task = asyncio.create_task(consume())
    # Give subscriber time to start and replay history
    await asyncio.sleep(0.05)

    # Emit a new event for job-A after subscription
    bus.emit("slurm", "new event for A", job_id="job-A")
    # Emit event for a different job (should be filtered out)
    bus.emit("slurm", "new event for B", job_id="job-B")

    await asyncio.wait_for(task, timeout=2.0)

    assert len(collected) == 3
    # First two are replayed from history, third is the live event
    assert collected[0].message == "job A event"
    assert collected[1].message == "job A event 2"
    assert collected[2].message == "new event for A"
    # All should have job_id == "job-A"
    for ev in collected:
        assert ev.job_id == "job-A"


@pytest.mark.asyncio
async def test_subscribe_job_replays_matching_history():
    bus = EventBus()
    bus.emit("agent", "event 1", job_id="target")
    bus.emit("agent", "event 2", job_id="other")
    bus.emit("agent", "event 3", job_id="target")

    collected = []

    async def consume():
        async for event in bus.subscribe_job("target"):
            collected.append(event)
            if len(collected) >= 2:
                break

    await asyncio.wait_for(consume(), timeout=2.0)

    assert len(collected) == 2
    assert collected[0].message == "event 1"
    assert collected[1].message == "event 3"


def test_check_job_connection_limit():
    bus = EventBus()
    # Fill up to the limit
    for _ in range(MAX_JOB_SSE_CONNECTIONS):
        bus._job_subscribers.append(asyncio.Queue())

    with pytest.raises(ConnectionError, match="Maximum job SSE connections"):
        bus.check_job_connection_limit()


def test_check_job_connection_limit_under():
    bus = EventBus()
    # Under the limit should not raise
    bus._job_subscribers.append(asyncio.Queue())
    bus.check_job_connection_limit()  # Should not raise
