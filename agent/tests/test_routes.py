"""Tests for route-level request models."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import pytest

from src.api.routes import ComputeSubmitRequest


def test_to_workspace_files_script():
    req = ComputeSubmitRequest(script="echo hello", nodes=1, time_limit_min=1)
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
        nodes=1,
        time_limit_min=1,
    )
    files, entrypoint = req.to_workspace_files()
    assert entrypoint == "main.py"
    assert len(files) == 2
    assert files[0]["path"] == "main.py"


def test_submission_mode_property():
    script_req = ComputeSubmitRequest(script="echo hello", nodes=1, time_limit_min=1)
    assert script_req.submission_mode == "script"

    multi_req = ComputeSubmitRequest(
        files=[{"path": "main.py", "content": "print('hi')"}],
        entrypoint="main.py",
        nodes=1,
        time_limit_min=1,
    )
    assert multi_req.submission_mode == "multi_file"
