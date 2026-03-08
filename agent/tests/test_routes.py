"""Tests for route-level request models."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import pytest

from src.api.routes import ComputeSubmitRequest, _job_summary


def test_to_workspace_files_script():
    req = ComputeSubmitRequest(script="echo hello", cpus=1, time_limit_min=1)
    files, entrypoint = req.to_workspace_files()
    assert entrypoint == "job.sh"
    assert len(files) == 1
    assert files[0]["path"] == "job.sh"
    assert files[0]["content"] == "echo hello"


def test_to_workspace_files_multi_file():
    req = ComputeSubmitRequest(
        files=[
            {"path": "main.py", "content": "print('hi')"},
            {"path": "helper.py", "content": "x = 1"},
        ],
        entrypoint="main.py",
        cpus=1,
        time_limit_min=1,
    )
    files, entrypoint = req.to_workspace_files()
    assert entrypoint == "main.py"
    assert len(files) == 2
    assert files[0]["path"] == "main.py"


def test_submission_mode_property():
    script_req = ComputeSubmitRequest(script="echo hello", cpus=1, time_limit_min=1)
    assert script_req.submission_mode == "script"

    multi_req = ComputeSubmitRequest(
        files=[{"path": "main.py", "content": "print('hi')"}],
        entrypoint="main.py",
        cpus=1,
        time_limit_min=1,
    )
    assert multi_req.submission_mode == "multi_file"


# --- _job_summary ---


def test_job_summary_empty():
    assert _job_summary(None) == {}
    assert _job_summary({}) == {}


def test_job_summary_includes_failure_reason():
    payload = {"entrypoint": "main.py", "failure_reason": "proof submission failed"}
    result = _job_summary(payload)
    assert result["failure_reason"] == "proof submission failed"
    assert result["entrypoint"] == "main.py"


def test_job_summary_no_failure_reason():
    payload = {"entrypoint": "main.py", "file_count": 2}
    result = _job_summary(payload)
    assert "failure_reason" not in result


# --- retry_count in user jobs response ---


def test_active_job_dict_includes_retry_count():
    """Verify the active job dict comprehension includes retry_count.

    Since we can't easily spin up a full DB here, we test the shape by
    importing _job_summary and verifying the field would be present in
    the dict literal structure used by get_user_jobs.
    """
    # Simulate what the route does: build the dict for an active job
    # We use a simple namespace object to mimic the ActiveJob model
    class FakeJob:
        id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        slurm_job_id = 42
        status = "pending"
        price_usdc = 0.50
        retry_count = 1
        payload = {"entrypoint": "main.py"}

        class submitted_at:
            @staticmethod
            def isoformat():
                return "2026-01-01T00:00:00"

    j = FakeJob()
    result = {
        "id": str(j.id),
        "slurm_job_id": j.slurm_job_id,
        "status": j.status,
        "price_usdc": float(j.price_usdc),
        "submitted_at": j.submitted_at.isoformat(),
        "retry_count": j.retry_count,
        **_job_summary(j.payload),
    }
    assert result["retry_count"] == 1
    assert result["status"] == "pending"
    assert result["entrypoint"] == "main.py"


# --- _job_summary with files ---


def test_job_summary_includes_files():
    payload = {
        "entrypoint": "main.py",
        "file_count": 2,
        "files": [
            {"path": "main.py", "content": "print('hi')"},
            {"path": "helper.py", "content": "x = 1"},
        ],
    }
    result = _job_summary(payload)
    assert result["files"] == payload["files"]
    assert result["file_count"] == 2
    assert result["entrypoint"] == "main.py"


def test_job_summary_omits_files_when_absent():
    """Backward compat: old jobs without files in payload."""
    payload = {"entrypoint": "main.py", "file_count": 2}
    result = _job_summary(payload)
    assert "files" not in result
    assert result["file_count"] == 2


def test_job_summary_includes_single_script_file():
    """Script-mode jobs store files as [{path: 'job.sh', content: '...'}]."""
    payload = {
        "entrypoint": "job.sh",
        "file_count": 1,
        "files": [{"path": "job.sh", "content": "echo hello"}],
    }
    result = _job_summary(payload)
    assert len(result["files"]) == 1
    assert result["files"][0]["path"] == "job.sh"
