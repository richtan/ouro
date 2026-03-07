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
