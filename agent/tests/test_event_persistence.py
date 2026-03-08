"""Tests for EventBus.get_job_events() — event persistence support."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from src.agent.event_bus import EventBus


def test_get_job_events_filters_by_job_id():
    bus = EventBus()
    bus.emit("agent", "processing job A", job_id="job-A")
    bus.emit("slurm", "submitted job A", job_id="job-A")
    bus.emit("agent", "processing job B", job_id="job-B")
    bus.emit("slurm", "completed job A", job_id="job-A")

    events = bus.get_job_events("job-A")
    assert len(events) == 3
    assert all(e["type"] in ("agent", "slurm") for e in events)
    assert events[0]["message"] == "processing job A"
    assert events[1]["message"] == "submitted job A"
    assert events[2]["message"] == "completed job A"
    # Each event has type, message, timestamp
    for e in events:
        assert set(e.keys()) == {"type", "message", "timestamp"}


def test_get_job_events_excludes_other_jobs():
    bus = EventBus()
    bus.emit("agent", "event for A", job_id="job-A")
    bus.emit("agent", "event for B", job_id="job-B")
    bus.emit("system", "global event")

    events_a = bus.get_job_events("job-A")
    assert len(events_a) == 1
    assert events_a[0]["message"] == "event for A"

    events_b = bus.get_job_events("job-B")
    assert len(events_b) == 1
    assert events_b[0]["message"] == "event for B"


def test_get_job_events_empty_for_unknown_job():
    bus = EventBus()
    bus.emit("agent", "some event", job_id="job-A")

    events = bus.get_job_events("nonexistent")
    assert events == []


def test_get_job_events_returns_serializable_dicts():
    bus = EventBus()
    bus.emit("agent", "test", job_id="job-1")

    events = bus.get_job_events("job-1")
    assert isinstance(events, list)
    assert isinstance(events[0], dict)
    # Should be JSON-serializable (no Pydantic models)
    import json
    json.dumps(events)  # Should not raise
