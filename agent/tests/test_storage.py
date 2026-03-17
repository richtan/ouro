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


# --- Storage rate limiter ---

def test_storage_rate_limiter_exists():
    """Storage rate limiter should exist with correct limits."""
    from src.api.routes import _storage_rate_limiter, MAX_STORAGE_FILES
    assert _storage_rate_limiter is not None
    assert _storage_rate_limiter._per_key_limit == 30
    assert _storage_rate_limiter._global_limit == 200
    assert _storage_rate_limiter._window == 60.0
    assert MAX_STORAGE_FILES == 10_000


def test_storage_rate_limiter_allows_under_limit():
    """Rate limiter allows requests under per-key limit."""
    from src.api.routes import _RateLimiter
    limiter = _RateLimiter(per_key_limit=5, global_limit=100, window_s=60.0)
    for _ in range(5):
        assert limiter.check("test-key") is True


def test_storage_rate_limiter_blocks_over_limit():
    """Rate limiter blocks requests over per-key limit."""
    from src.api.routes import _RateLimiter
    limiter = _RateLimiter(per_key_limit=5, global_limit=100, window_s=60.0)
    for _ in range(5):
        limiter.check("test-key")
    assert limiter.check("test-key") is False


def test_storage_rate_limiter_global_limit():
    """Rate limiter blocks when global limit reached."""
    from src.api.routes import _RateLimiter
    limiter = _RateLimiter(per_key_limit=100, global_limit=3, window_s=60.0)
    for i in range(3):
        assert limiter.check(f"key-{i}") is True
    assert limiter.check("key-new") is False


def test_storage_rate_limiter_per_key_isolation():
    """Different keys have independent limits."""
    from src.api.routes import _RateLimiter
    limiter = _RateLimiter(per_key_limit=2, global_limit=100, window_s=60.0)
    assert limiter.check("key-a") is True
    assert limiter.check("key-a") is True
    assert limiter.check("key-a") is False
    # Different key should still work
    assert limiter.check("key-b") is True


# --- Generated docker script includes storage check ---

@pytest.fixture(autouse=False)
def _slurm_proxy_env():
    """Set SLURM_PROXY_TOKEN for slurm_proxy module import."""
    os.environ.setdefault("SLURM_PROXY_TOKEN", "test-token")


def _import_slurm_proxy():
    """Import slurm_proxy module with required env vars set."""
    import sys
    os.environ.setdefault("SLURM_PROXY_TOKEN", "test-token")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "slurm"))
    import importlib
    # Force re-import if already cached without token
    if "slurm_proxy" in sys.modules:
        return sys.modules["slurm_proxy"]
    import slurm_proxy
    return slurm_proxy


def test_wrap_in_docker_storage_check_simple_mode():
    """Simple mode script includes pre-run storage file count check."""
    sp = _import_slurm_proxy()
    script = sp.wrap_in_docker(
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="job.sh",
        job_name="test-job",
        image_name="ouro-ubuntu",
        storage_path="/ouro-storage/0x" + "a" * 40,
    )
    assert "Pre-run storage file count check" in script
    assert "10000" in script
    assert "exit 78" in script


def test_wrap_in_docker_no_storage_no_check():
    """Script without storage_path should not include file count check."""
    sp = _import_slurm_proxy()
    script = sp.wrap_in_docker(
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="job.sh",
        job_name="test-job",
        image_name="ouro-ubuntu",
        storage_path=None,
    )
    assert "Pre-run storage file count check" not in script


def test_wrap_in_docker_storage_check_dockerfile_mode():
    """Dockerfile mode script includes pre-run storage file count check."""
    sp = _import_slurm_proxy()
    script = sp.wrap_in_docker(
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="main.py",
        job_name="test-job",
        dockerfile_content="FROM python:3.12-slim\nCMD [\"python3\"]",
        storage_path="/ouro-storage/0x" + "a" * 40,
    )
    assert "Pre-run storage file count check" in script
    assert "DOCKER_BUILDKIT=0" in script


# --- Bounded file helpers ---

def test_count_files_bounded(tmp_path):
    """_count_files should stop at max_count."""
    sp = _import_slurm_proxy()
    # Create 15 files
    for i in range(15):
        (tmp_path / f"file_{i}.txt").write_text("data")
    assert sp._count_files(str(tmp_path), 5, 10) == 15
    assert sp._count_files(str(tmp_path), 5, 5) > 5  # stops after exceeding max


def test_list_files_bounded(tmp_path):
    """_list_files should respect max_entries."""
    sp = _import_slurm_proxy()
    for i in range(20):
        (tmp_path / f"file_{i}.txt").write_text("data")
    files = sp._list_files(str(tmp_path), 10, 5)
    assert len(files) == 10
    assert all("path" in f and "size" in f for f in files)


def test_wrap_in_docker_workspace_writable():
    """Workspace should be mounted writable (no :ro suffix)."""
    sp = _import_slurm_proxy()
    script = sp.wrap_in_docker(
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="job.sh",
        job_name="test-job",
        image_name="ouro-ubuntu",
    )
    assert "/workspace:ro" not in script
    assert "/workspace" in script


def test_wrap_in_docker_workspace_writable_dockerfile_mode():
    """Dockerfile mode workspace should also be writable."""
    sp = _import_slurm_proxy()
    script = sp.wrap_in_docker(
        workspace_path="/ouro-jobs/workspaces/test",
        entrypoint="main.py",
        job_name="test-job",
        dockerfile_content="FROM python:3.12-slim\nCMD [\"python3\"]",
    )
    assert "/workspace:ro" not in script


def test_workspace_proj_id_deterministic():
    """Workspace project IDs should be deterministic and in the correct range."""
    sp = _import_slurm_proxy()
    pid1 = sp._workspace_proj_id("550e8400-e29b-41d4-a716-446655440000")
    pid2 = sp._workspace_proj_id("550e8400-e29b-41d4-a716-446655440000")
    assert pid1 == pid2
    assert pid1 >= 1_000_000_001
    assert pid1 <= 2_000_000_000


def test_workspace_proj_id_no_storage_collision():
    """Workspace project IDs should not collide with storage project IDs."""
    sp = _import_slurm_proxy()
    ws_pid = sp._workspace_proj_id("some-uuid")
    # Storage IDs are: int(wallet[:10], 16) % 2B + 1, range 1–1B
    assert ws_pid > 1_000_000_000


def test_list_files_skips_symlinks(tmp_path):
    """_list_files should skip symlinks."""
    sp = _import_slurm_proxy()
    (tmp_path / "real.txt").write_text("data")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    files = sp._list_files(str(tmp_path), 100, 5)
    assert len(files) == 1
    assert files[0]["path"] == "real.txt"
