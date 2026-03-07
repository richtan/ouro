"""Tests for workspace file validation and route models."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import pytest
from pydantic import ValidationError

from src.api.routes import (
    ComputeSubmitRequest,
    CreateSessionRequest,
    WorkspaceFile,
    _job_summary,
    _validate_image,
    _validate_workspace_file_path,
)


# --- _validate_workspace_file_path ---


def test_valid_file_path():
    _validate_workspace_file_path("main.py")
    _validate_workspace_file_path("src/utils.py")
    _validate_workspace_file_path("dir/sub/file.txt")


def test_reject_path_traversal():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_workspace_file_path("../etc/passwd")


def test_reject_absolute_path():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_workspace_file_path("/etc/passwd")


def test_reject_null_bytes():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_workspace_file_path("main\x00.py")


def test_reject_deep_path():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_workspace_file_path("a/b/c/d/e/f/g.py")


# --- _validate_image ---


def test_valid_image():
    _validate_image("ouro-ubuntu")
    _validate_image("ouro-python")
    _validate_image(None)


def test_invalid_image():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_image("not_a_real_image")


# --- ComputeSubmitRequest ---


def test_script_mode():
    req = ComputeSubmitRequest(script="echo hello")
    assert req.submission_mode == "script"


def test_multi_file_mode():
    req = ComputeSubmitRequest(
        files=[WorkspaceFile(path="main.py", content="print(1)")],
        entrypoint="main.py",
    )
    assert req.submission_mode == "multi_file"


def test_no_mode_raises():
    with pytest.raises(ValidationError):
        ComputeSubmitRequest()


def test_both_modes_raises():
    with pytest.raises(ValidationError):
        ComputeSubmitRequest(
            script="echo hello",
            files=[WorkspaceFile(path="main.py", content="print(1)")],
            entrypoint="main.py",
        )


def test_files_without_entrypoint_raises():
    with pytest.raises(ValidationError):
        ComputeSubmitRequest(
            files=[WorkspaceFile(path="main.py", content="print(1)")],
        )


def test_max_files_exceeded():
    with pytest.raises(ValidationError):
        ComputeSubmitRequest(
            files=[WorkspaceFile(path=f"f{i}.py", content="x") for i in range(101)],
            entrypoint="f0.py",
        )


def test_image_field():
    req = ComputeSubmitRequest(script="echo hello", image="ouro-python")
    assert req.image == "ouro-python"


# --- CreateSessionRequest ---


def test_session_script():
    req = CreateSessionRequest(script="echo hello")
    assert req.script == "echo hello"


def test_session_job_payload():
    req = CreateSessionRequest(job_payload={"submission_mode": "multi_file", "entrypoint": "main.py"})
    assert req.job_payload is not None


def test_session_empty_raises():
    with pytest.raises(ValidationError):
        CreateSessionRequest()


# --- _job_summary ---


def test_job_summary_script():
    """Legacy script payloads include the script key."""
    result = _job_summary({"script": "echo hi"})
    assert result["script"] == "echo hi"


def test_job_summary_multi_file():
    result = _job_summary({
        "entrypoint": "main.py",
        "file_count": 3,
        "image": "ouro-python",
    })
    assert result["entrypoint"] == "main.py"
    assert result["file_count"] == 3
    assert result["image"] == "ouro-python"


def test_job_summary_none():
    result = _job_summary(None)
    assert result == {}


def test_job_summary_legacy():
    """Legacy payloads with script key are handled."""
    result = _job_summary({"script": "echo old"})
    assert result["script"] == "echo old"


def test_job_summary_new_format():
    """New unified payloads have entrypoint + file_count."""
    result = _job_summary({"entrypoint": "job.sh", "file_count": 1, "image": "ouro-ubuntu"})
    assert result["entrypoint"] == "job.sh"
    assert result["file_count"] == 1
    assert "image" not in result  # ouro-ubuntu is excluded


def test_job_summary_script_with_image():
    """Non-default image is included."""
    result = _job_summary({"script": "echo hi", "image": "ouro-python"})
    assert result["image"] == "ouro-python"

    # Default image should not appear
    result2 = _job_summary({"script": "echo hi", "image": "ouro-ubuntu"})
    assert "image" not in result2
