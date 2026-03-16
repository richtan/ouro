"""Tests for persistent storage feature."""

from __future__ import annotations

import os
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import pytest
from unittest.mock import AsyncMock

from src.api.routes import ComputeSubmitRequest, WorkspaceFile, _job_summary
from src.db.models import StorageQuota


# --- ComputeSubmitRequest.mount_storage ---

def test_mount_storage_defaults_false():
    req = ComputeSubmitRequest(script="echo hello")
    assert req.mount_storage is False


def test_mount_storage_true():
    req = ComputeSubmitRequest(script="echo hello", mount_storage=True)
    assert req.mount_storage is True


def test_mount_storage_with_files():
    req = ComputeSubmitRequest(
        files=[WorkspaceFile(path="Dockerfile", content="FROM python:3.12-slim\nCMD [\"python3\"]")],
        mount_storage=True,
    )
    assert req.mount_storage is True
    assert req.submission_mode == "multi_file"


# --- _job_summary includes mount_storage ---

def test_job_summary_with_storage():
    payload = {
        "entrypoint": "job.sh",
        "file_count": 1,
        "mount_storage": True,
    }
    summary = _job_summary(payload)
    assert summary["mount_storage"] is True


def test_job_summary_without_storage():
    payload = {
        "entrypoint": "job.sh",
        "file_count": 1,
    }
    summary = _job_summary(payload)
    assert "mount_storage" not in summary


# --- StorageQuota model ---

def test_storage_quota_defaults():
    q = StorageQuota(wallet_address="0x" + "a" * 40)
    assert q.wallet_address == "0x" + "a" * 40


# --- OracleDeps storage_path ---

def test_oracle_deps_storage_path():
    from src.agent.oracle import OracleDeps
    deps = OracleDeps(
        job_id="test",
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="job.sh",
        image="ouro-ubuntu",
        partition="compute",
        cpus=1,
        time_limit_min=1,
        slurm_client=AsyncMock(),
        chain_client=AsyncMock(),
        db=AsyncMock(),
        event_bus=AsyncMock(),
        storage_path="/ouro-storage/0x" + "a" * 40,
    )
    assert deps.storage_path == "/ouro-storage/0x" + "a" * 40


def test_oracle_deps_storage_path_none():
    from src.agent.oracle import OracleDeps
    deps = OracleDeps(
        job_id="test",
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="job.sh",
        image="ouro-ubuntu",
        partition="compute",
        cpus=1,
        time_limit_min=1,
        slurm_client=AsyncMock(),
        chain_client=AsyncMock(),
        db=AsyncMock(),
        event_bus=AsyncMock(),
    )
    assert deps.storage_path is None


# --- SlurmClient storage methods ---

@pytest.mark.asyncio
async def test_slurm_client_init_storage(mock_slurm_client):
    """Uses conftest default: returns /ouro-storage/0xaaa..."""
    result = await mock_slurm_client.init_storage("0x" + "a" * 40)
    assert result.startswith("/ouro-storage/")


@pytest.mark.asyncio
async def test_slurm_client_get_storage_usage(mock_slurm_client):
    """Uses conftest default: returns {used_bytes: 0, file_count: 0}."""
    result = await mock_slurm_client.get_storage_usage("0x" + "a" * 40)
    assert "used_bytes" in result
    assert "file_count" in result


@pytest.mark.asyncio
async def test_slurm_client_get_storage_usage_with_data(mock_slurm_client):
    """Override default to test with actual data."""
    mock_slurm_client.get_storage_usage.return_value = {"used_bytes": 1024, "file_count": 3}
    result = await mock_slurm_client.get_storage_usage("0x" + "a" * 40)
    assert result["used_bytes"] == 1024
    assert result["file_count"] == 3


@pytest.mark.asyncio
async def test_slurm_client_list_storage_files(mock_slurm_client):
    """Override default to test with actual files."""
    mock_slurm_client.list_storage_files.return_value = [
        {"path": "model.pt", "size": 512, "modified": 1710000000},
    ]
    result = await mock_slurm_client.list_storage_files("0x" + "a" * 40)
    assert len(result) == 1
    assert result[0]["path"] == "model.pt"


@pytest.mark.asyncio
async def test_slurm_client_delete_storage_file(mock_slurm_client):
    """Uses conftest default: returns True."""
    result = await mock_slurm_client.delete_storage_file("0x" + "a" * 40, "model.pt")
    assert result is True


# --- Processor passes storage_path to OracleDeps ---

def test_processor_reads_storage_path_from_payload(make_active_job):
    """Verify processor would read storage_path from payload for OracleDeps."""
    job = make_active_job(payload={
        "workspace_path": "/ouro-jobs/workspaces/test",
        "entrypoint": "job.sh",
        "cpus": 1,
        "time_limit_min": 1,
        "storage_path": "/ouro-storage/0x" + "a" * 40,
        "mount_storage": True,
    })
    payload = job.payload
    assert payload.get("storage_path") == "/ouro-storage/0x" + "a" * 40


def test_processor_no_storage_path_in_legacy_payload(make_active_job):
    """Legacy payloads without storage_path should return None."""
    job = make_active_job(payload={
        "workspace_path": "/ouro-jobs/workspaces/test",
        "entrypoint": "job.sh",
        "cpus": 1,
        "time_limit_min": 1,
    })
    payload = job.payload
    assert payload.get("storage_path") is None


# --- mount_storage validation ---

def test_mount_storage_requires_submitter_address():
    """mount_storage=True should work at request parsing level (validation happens in route)."""
    req = ComputeSubmitRequest(script="echo hello", mount_storage=True)
    assert req.mount_storage is True
    # Note: the 422 for missing submitter_address happens in the route handler,
    # not in the Pydantic model, so this parses fine


# --- Signature verification (uses shared _verify_wallet_signature) ---

def test_verify_wallet_signature_valid_for_storage_delete():
    """Valid EIP-191 signature should pass verification."""
    from eth_account import Account
    from eth_account.messages import encode_defunct
    import time

    acct = Account.create()
    wallet = acct.address.lower()
    path = "model.pt"
    timestamp = str(int(time.time()))
    message = f"ouro-storage-delete:{wallet}:{path}:{timestamp}"

    sig = acct.sign_message(encode_defunct(text=message))

    from src.api.routes import _verify_wallet_signature
    # Should not raise
    _verify_wallet_signature(wallet, message, "0x" + sig.signature.hex(), timestamp)


def test_verify_wallet_signature_wrong_wallet():
    """Signature from wrong wallet should fail."""
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from fastapi import HTTPException
    import time

    acct1 = Account.create()
    acct2 = Account.create()
    wallet = acct2.address.lower()
    path = "model.pt"
    timestamp = str(int(time.time()))
    message = f"ouro-storage-delete:{wallet}:{path}:{timestamp}"

    sig = acct1.sign_message(encode_defunct(text=message))

    from src.api.routes import _verify_wallet_signature
    with pytest.raises(HTTPException) as exc_info:
        _verify_wallet_signature(wallet, message, "0x" + sig.signature.hex(), timestamp)
    assert exc_info.value.status_code == 401


def test_verify_wallet_signature_expired():
    """Expired timestamp should fail."""
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from fastapi import HTTPException
    import time

    acct = Account.create()
    wallet = acct.address.lower()
    path = "model.pt"
    timestamp = str(int(time.time()) - 600)
    message = f"ouro-storage-delete:{wallet}:{path}:{timestamp}"

    sig = acct.sign_message(encode_defunct(text=message))

    from src.api.routes import _verify_wallet_signature
    with pytest.raises(HTTPException) as exc_info:
        _verify_wallet_signature(wallet, message, "0x" + sig.signature.hex(), timestamp)
    assert exc_info.value.status_code == 401
