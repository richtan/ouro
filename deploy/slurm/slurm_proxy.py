"""Slurm REST proxy — wraps real sbatch/scontrol/sinfo with Docker isolation.

Maintains the same API the Ouro agent expects (slurmrestd v0.0.38 compatible)
so the agent's SlurmClient needs zero changes.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import fcntl
import tempfile
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_ALLOWED_CWD = {"/tmp"}
MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB
_WORKSPACE_PATH_RE = re.compile(r"^/ouro-jobs/workspaces/[a-zA-Z0-9_-]+$")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slurm_proxy")

JWT_TOKEN = os.environ.get("SLURM_PROXY_TOKEN", "")
if not JWT_TOKEN:
    raise SystemExit("SLURM_PROXY_TOKEN is empty — refusing to start without auth token")

app = FastAPI(title="Ouro Slurm Proxy")

OUTPUT_DIR = "/ouro-jobs/output"
SCRIPTS_DIR = "/ouro-jobs/scripts"
WORKSPACE_BASE_DIR = "/ouro-jobs/workspaces"
STORAGE_BASE_DIR = "/ouro-storage"
_STORAGE_WALLET_RE = re.compile(r"^0x[0-9a-f]{40}$")

MAX_STORAGE_FILES = 10_000  # NOTE: must match agent/src/api/routes.py MAX_STORAGE_FILES
STORAGE_QUOTA_BYTES = 1_073_741_824  # 1GB — matches DB default in config.py

MAX_WORKSPACE_BYTES = 500 * 1024 * 1024  # 500MB per workspace
MAX_WORKSPACE_FILES = 10_000
_WORKSPACE_PROJ_ID_OFFSET = 1_000_000_001  # Workspace proj IDs start here (storage uses 1–1B)


def _validate_storage_wallet(wallet: str) -> str:
    """Validate wallet address and return its storage directory path.
    Raises HTTPException on invalid input or path traversal."""
    if not _STORAGE_WALLET_RE.match(wallet):
        raise HTTPException(400, "Invalid wallet address format (expected lowercase 0x + 40 hex)")
    storage_path = os.path.join(STORAGE_BASE_DIR, wallet)
    real = os.path.realpath(storage_path)
    if not real.startswith(os.path.realpath(STORAGE_BASE_DIR) + os.sep):
        raise HTTPException(400, "Path traversal detected")
    return real


def _append_if_missing(fpath: str, line: str) -> None:
    """Append a line to a file if not already present, with file locking."""
    try:
        with open(fpath, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            content = f.read()
            if line not in content:
                f.write(line + "\n")
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError as e:
        logger.warning("Failed to update %s: %s", fpath, e)


def _setup_project_quota(storage_path: str, wallet: str) -> None:
    """Assign ext4 project quota to a wallet's storage directory.

    Uses ext4 project quotas for kernel-level inode + byte limits.
    Idempotent — safe to call on every init_storage request.
    Failures are non-fatal (logged as warnings) so the proxy works
    without quotas in degraded mode.
    """
    proj_id = int(wallet[:10], 16) % 2_000_000_000 + 1

    try:
        with open("/etc/projects", "r") as f:
            for existing_line in f:
                existing_line = existing_line.strip()
                if not existing_line or ":" not in existing_line:
                    continue
                existing_id, existing_path = existing_line.split(":", 1)
                if int(existing_id) == proj_id and existing_path != storage_path:
                    proj_id = (proj_id + 1) % 2_000_000_000 + 1
                    logger.warning(
                        "Project ID collision for %s, using %d instead", wallet, proj_id
                    )
                    break
    except OSError:
        pass

    _append_if_missing("/etc/projects", f"{proj_id}:{storage_path}")
    _append_if_missing("/etc/projid", f"{proj_id}:ouro_{wallet[:10]}")

    try:
        subprocess.run(
            ["chattr", "+P", "-p", str(proj_id), storage_path],
            capture_output=True, timeout=5, check=False,
        )

        for dirpath, _, filenames in os.walk(storage_path, followlinks=False):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if not os.path.islink(fpath):
                    subprocess.run(
                        ["chattr", "-p", str(proj_id), fpath],
                        capture_output=True, timeout=5, check=False,
                    )

        block_limit = STORAGE_QUOTA_BYTES // 1024
        subprocess.run(
            [
                "setquota", "-P", str(proj_id),
                "0", str(block_limit),
                "0", str(MAX_STORAGE_FILES),
                "/",
            ],
            capture_output=True, timeout=5, check=False,
        )
        logger.info(
            "Project quota set for %s: proj_id=%d, blocks=%d, inodes=%d",
            wallet, proj_id, block_limit, MAX_STORAGE_FILES,
        )
    except Exception as e:
        logger.warning("Failed to set project quota for %s: %s", wallet, e)


def _workspace_proj_id(workspace_id: str) -> int:
    """Deterministic project ID for a workspace UUID. Range: 1B+1 to 2B."""
    h = int(hashlib.sha256(workspace_id.encode()).hexdigest()[:8], 16)
    return h % 1_000_000_000 + _WORKSPACE_PROJ_ID_OFFSET


def _setup_workspace_quota(workspace_path: str, workspace_id: str) -> int | None:
    """Set up ephemeral ext4 project quota for a workspace. Returns proj_id on success."""
    proj_id = _workspace_proj_id(workspace_id)
    try:
        _append_if_missing("/etc/projects", f"{proj_id}:{workspace_path}")
        _append_if_missing("/etc/projid", f"{proj_id}:ws_{workspace_id[:8]}")

        subprocess.run(
            ["chattr", "+P", "-p", str(proj_id), workspace_path],
            capture_output=True, timeout=5, check=False,
        )
        block_limit = MAX_WORKSPACE_BYTES // 1024
        subprocess.run(
            [
                "setquota", "-P", str(proj_id),
                "0", str(block_limit),
                "0", str(MAX_WORKSPACE_FILES),
                "/",
            ],
            capture_output=True, timeout=5, check=False,
        )
        logger.info("Workspace quota set: %s proj_id=%d", workspace_id[:8], proj_id)
        return proj_id
    except Exception as e:
        logger.warning("Failed to set workspace quota for %s: %s", workspace_id[:8], e)
        return None


def _remove_line_from_file(fpath: str, prefix: str) -> None:
    """Remove lines starting with prefix from a file, with file locking."""
    try:
        with open(fpath, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            lines = f.readlines()
            f.seek(0)
            f.truncate()
            for line in lines:
                if not line.startswith(prefix):
                    f.write(line)
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError as e:
        logger.warning("Failed to update %s: %s", fpath, e)


def _remove_workspace_quota(workspace_id: str) -> None:
    """Remove ephemeral project quota for a deleted workspace."""
    proj_id = _workspace_proj_id(workspace_id)
    try:
        # Zero out quota first
        subprocess.run(
            ["setquota", "-P", str(proj_id), "0", "0", "0", "0", "/"],
            capture_output=True, timeout=5, check=False,
        )
        # Remove entries from /etc/projects and /etc/projid
        _remove_line_from_file("/etc/projects", f"{proj_id}:")
        _remove_line_from_file("/etc/projid", f"{proj_id}:")
        logger.info("Workspace quota removed: %s proj_id=%d", workspace_id[:8], proj_id)
    except Exception as e:
        logger.warning("Failed to remove workspace quota for %s: %s", workspace_id[:8], e)


DOCKER_IMAGES = {
    "ouro-ubuntu": "ubuntu:22.04",
    "ouro-python": "python:3.12-slim",
    "ouro-nodejs": "node:20-slim",
}


def check_auth(token: str | None):
    if not JWT_TOKEN:
        raise HTTPException(401, "Authentication not configured")
    if not token or not hmac.compare_digest(token, JWT_TOKEN):
        raise HTTPException(401, "Authentication failure")


async def run_cmd(cmd: list[str], env: dict | None = None) -> str:
    merged = {**os.environ, **(env or {})}
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_msg = stderr.decode().strip()
        logger.error("Command %s failed (rc=%d): %s", cmd, proc.returncode, err_msg)
        raise HTTPException(500, "Command execution failed")
    return stdout.decode()


def parse_time_limit(tl) -> str:
    if isinstance(tl, dict):
        seconds = tl.get("number", 300)
        minutes = max(1, seconds // 60)
        return str(minutes)
    return str(tl)


def resolve_docker_image(name: str | None) -> str:
    """Map image alias to Docker Hub reference."""
    if not name or name == "ouro-ubuntu":
        return DOCKER_IMAGES["ouro-ubuntu"]
    image = DOCKER_IMAGES.get(name)
    if not image:
        raise HTTPException(400, f"Unknown image: {name}. Allowed: {', '.join(sorted(DOCKER_IMAGES))}")
    return image


def _validate_workspace_file_path(workspace_path: str, rel_path: str) -> str:
    """Validate and return the absolute path for a workspace file. Raises HTTPException on violation."""
    if "\x00" in rel_path:
        raise HTTPException(400, "Null bytes in file path")
    normalized = os.path.normpath(rel_path)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise HTTPException(400, f"Invalid file path: {rel_path}")
    if normalized.count(os.sep) > 5:
        raise HTTPException(400, f"File path too deep: {rel_path}")
    abs_path = os.path.realpath(os.path.join(workspace_path, normalized))
    if not abs_path.startswith(os.path.realpath(workspace_path) + os.sep):
        raise HTTPException(400, f"Path traversal detected: {rel_path}")
    return abs_path


def _validate_and_write_file(workspace_path: str, rel_path: str, content: str) -> None:
    """Validate path and write file content to workspace."""
    abs_path = _validate_workspace_file_path(workspace_path, rel_path)
    parent = os.path.dirname(abs_path)
    os.makedirs(parent, exist_ok=True)
    os.chmod(parent, 0o755)
    with open(abs_path, "w") as f:
        f.write(content)
    os.chmod(abs_path, 0o644)


def _storage_check_block(storage_path: str | None) -> str:
    """Generate a pre-run file count check block for the job script."""
    if not storage_path:
        return ""
    sp = shlex.quote(storage_path)
    return f"""# Pre-run storage file count check (UX hint — kernel quotas enforce the real limit)
if [ -d {sp} ]; then
  _FC=$(find {sp} -type f -maxdepth 5 ! -type l 2>/dev/null | head -10001 | wc -l)
  if [ "$_FC" -gt {MAX_STORAGE_FILES} ]; then
    echo "ERROR: Storage file limit exceeded ($_FC files, max {MAX_STORAGE_FILES}). Delete files at /scratch before running new jobs." >&2
    exit 78
  fi
fi
"""


def wrap_in_docker(
    workspace_path: str,
    entrypoint: str,
    job_name: str,
    image_name: str | None = None,
    docker_image: str | None = None,
    entrypoint_cmd: list[str] | None = None,
    dockerfile_content: str | None = None,
    cpus: str = "1",
    memory_mb: int = 1600,
    storage_path: str | None = None,
) -> str:
    """Generate a wrapper script for Docker execution on the worker."""
    # For dockerfile builds, image_ref is unused (we docker build a custom tag).
    # Skip resolve_docker_image to avoid rejecting raw Docker Hub names like "ubuntu:22.04".
    if dockerfile_content:
        image_ref = docker_image or image_name or "unused"
    else:
        image_ref = docker_image or resolve_docker_image(image_name)

    sec_flags = " \\\n    ".join([
        "--read-only",
        "--network none",
        "--cap-drop ALL",
        "--user 65534:65534",
        "--ipc=private",
        "--security-opt no-new-privileges=true",
        '--entrypoint ""',
        "--tmpfs /tmp:rw,noexec,nosuid,size=100m",
        "--tmpfs /dev/shm:rw,noexec,nosuid,size=64m",
        f"--cpus={cpus}",
        f"--memory={memory_mb}m",
        f"--memory-swap={memory_mb}m",
        "--pids-limit=4096",
        "--ulimit nofile=1024:2048",
        "--log-driver none",
        "--rm",
    ])

    storage_mount = ""
    if storage_path:
        # Validate path format to prevent injection
        if not re.match(r"^/ouro-storage/0x[0-9a-f]{40}$", storage_path):
            raise HTTPException(400, "Invalid storage path format")
        storage_mount = f"-v {shlex.quote(storage_path)}:/scratch \\\n    "

    if dockerfile_content:
        # Complex Dockerfile: docker build on worker, then run
        if entrypoint_cmd:
            cmd_str = " ".join(shlex.quote(p) for p in entrypoint_cmd)
        else:
            normalized = os.path.normpath(entrypoint)
            if normalized.startswith("..") or normalized.startswith("/") or "\x00" in entrypoint:
                raise HTTPException(400, "Invalid entrypoint path")
            ext = os.path.splitext(normalized)[1].lower()
            executor = {".py": "python3", ".r": "Rscript", ".jl": "julia"}.get(ext, "bash")
            cmd_str = f"{executor} {shlex.quote(f'/workspace/{normalized}')}"

        tag = f"ouro-custom-{shlex.quote(job_name)}"
        return f"""#!/bin/bash
set -euo pipefail
DOCKER_TAG={tag}
cd {shlex.quote(workspace_path)}
{_storage_check_block(storage_path)}_BUILD_LOG=$(mktemp)
if ! DOCKER_BUILDKIT=0 docker build -t "$DOCKER_TAG" -f Dockerfile . >"$_BUILD_LOG" 2>&1; then
  echo "ERROR: Docker build failed. Last 50 lines of build log:" >&2
  tail -50 "$_BUILD_LOG" >&2
  rm -f "$_BUILD_LOG"
  exit 1
fi
rm -f "$_BUILD_LOG"
docker run \\
    {sec_flags} \\
    {storage_mount}-v {shlex.quote(workspace_path)}:/workspace \\
    -w /workspace \\
    "$DOCKER_TAG" \\
    {cmd_str}
EXIT_CODE=$?
docker rmi "$DOCKER_TAG" >/dev/null 2>&1 || true
exit $EXIT_CODE
"""

    # Simple mode: pull + run
    if entrypoint_cmd:
        cmd_str = " ".join(shlex.quote(p) for p in entrypoint_cmd)
    else:
        normalized = os.path.normpath(entrypoint)
        if normalized.startswith("..") or normalized.startswith("/") or "\x00" in entrypoint:
            raise HTTPException(400, "Invalid entrypoint path")
        ext = os.path.splitext(normalized)[1].lower()
        executor = {".py": "python3", ".r": "Rscript", ".jl": "julia"}.get(ext, "bash")
        cmd_str = f"{executor} {shlex.quote(f'/workspace/{normalized}')}"

    is_prebuilt = image_ref in DOCKER_IMAGES.values()
    cleanup_line = f"\ndocker rmi {shlex.quote(image_ref)} >/dev/null 2>&1 || true" if not is_prebuilt else ""

    return f"""#!/bin/bash
set -euo pipefail
{_storage_check_block(storage_path)}docker pull -q {shlex.quote(image_ref)} >/dev/null 2>&1 || true
docker run \\
    {sec_flags} \\
    {storage_mount}-v {shlex.quote(workspace_path)}:/workspace \\
    -w /workspace \\
    {shlex.quote(image_ref)} \\
    {cmd_str}
EXIT_CODE=$?{cleanup_line}
exit $EXIT_CODE
"""


@app.post("/slurm/v0.0.37/job/submit")
@app.post("/slurm/v0.0.38/job/submit")
async def submit_job(
    request: Request, x_slurm_user_token: str | None = Header(None)
):
    check_auth(x_slurm_user_token)
    body = await request.json()
    logger.info("Job submit payload: %s", json.dumps(body)[:500])

    image_name = body.get("image")

    job = body.get("job", {})
    partition = "compute"
    name = job.get("name", "ouro-job")
    cpus = str(job.get("cpus", "1"))
    time_limit = parse_time_limit(job.get("time_limit", "5"))
    cwd = job.get("current_working_directory", "/tmp")

    # V11: Validate job name against injection
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(400, "Invalid job name")
    # V12: Validate working directory
    if cwd not in _ALLOWED_CWD:
        raise HTTPException(400, "Invalid working directory")

    workspace_path = body.get("workspace_path")
    entrypoint = body.get("entrypoint")

    # Transition fallback: old agent may still send script-only payloads
    # until it's redeployed with the unified workspace model.
    if not workspace_path and body.get("script"):
        logger.warning("Legacy script-mode submission — creating inline workspace")
        script = body["script"]
        if not script.startswith("#!"):
            script = "#!/bin/bash\n" + script
        ws_id = str(uuid.uuid4())
        workspace_path = os.path.join(WORKSPACE_BASE_DIR, ws_id)
        os.makedirs(workspace_path, mode=0o755, exist_ok=True)
        os.chmod(workspace_path, 0o755)
        script_path = os.path.join(workspace_path, "job.sh")
        with open(script_path, "w") as sf:
            sf.write(script)
        os.chmod(script_path, 0o644)
        os.chown(workspace_path, 65534, 65534)
        os.chown(script_path, 65534, 65534)
        proj_id = _setup_workspace_quota(workspace_path, ws_id)
        if proj_id is None:
            shutil.rmtree(workspace_path, ignore_errors=True)
            raise HTTPException(500, "Failed to set up workspace quota")
        entrypoint = "job.sh"

    docker_image = body.get("docker_image")
    dockerfile_content = body.get("dockerfile_content")
    entrypoint_cmd = body.get("entrypoint_cmd")
    storage_path = body.get("storage_path")
    # Validate storage path if present
    if storage_path and not re.match(r"^/ouro-storage/0x[0-9a-f]{40}$", storage_path):
        raise HTTPException(400, "Invalid storage_path format")

    if not workspace_path or (not entrypoint and not entrypoint_cmd):
        raise HTTPException(400, "workspace_path and entrypoint (or entrypoint_cmd) required")

    # Write validated dockerfile_content to workspace to prevent naming discrepancy attacks
    if dockerfile_content:
        df_path = os.path.join(workspace_path, "Dockerfile")
        with open(df_path, "w") as f:
            f.write(dockerfile_content)
        os.chown(df_path, 65534, 65534)
        # Remove any case-variant duplicates
        for variant in ("dockerfile", "DOCKERFILE"):
            variant_path = os.path.join(workspace_path, variant)
            if variant_path != df_path and os.path.exists(variant_path):
                os.remove(variant_path)

    # Add time buffer for Docker pull/build (not charged to user)
    docker_buffer = 5 if dockerfile_content else 2
    adjusted_time = str(int(time_limit) + docker_buffer)

    wrapper_script = wrap_in_docker(
        workspace_path, entrypoint or "", name, image_name,
        docker_image=docker_image,
        entrypoint_cmd=entrypoint_cmd,
        dockerfile_content=dockerfile_content,
        cpus=cpus,
        memory_mb=1600 * int(cpus),
        storage_path=storage_path,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, dir="/tmp"
    ) as f:
        f.write(wrapper_script)
        wrapper_path = f.name
    os.chmod(wrapper_path, 0o755)

    logger.info(
        "Submitting: partition=%s name=%s cpus=%s time=%s isolation=docker",
        partition, name, cpus, adjusted_time,
    )

    try:
        result = await run_cmd(
            [
                "sbatch",
                "--parsable",
                f"--partition={partition}",
                f"--job-name={name}",
                "--ntasks=1",
                f"--cpus-per-task={cpus}",
                "--mem-per-cpu=1600M",
                f"--time={adjusted_time}",
                f"--output={OUTPUT_DIR}/slurm-%j.out",
                f"--error={OUTPUT_DIR}/slurm-%j.err",
                f"--chdir={cwd}",
                wrapper_path,
            ]
        )
        job_id = int(result.strip())
        logger.info("Job submitted: %d (isolation: docker)", job_id)
        return {"job_id": job_id, "step_id": "batch", "error_code": 0, "error": ""}
    except Exception as e:
        logger.error("Submit failed: %s", e)
        raise
    finally:
        try:
            os.unlink(wrapper_path)
        except Exception:
            pass


@app.get("/slurm/v0.0.37/job/{job_id}")
@app.get("/slurm/v0.0.38/job/{job_id}")
async def get_job(
    job_id: int, x_slurm_user_token: str | None = Header(None)
):
    check_auth(x_slurm_user_token)
    try:
        result = await run_cmd(
            ["scontrol", "show", "job", str(job_id), "--oneliner"]
        )
    except HTTPException:
        return {
            "jobs": [
                {
                    "job_id": job_id,
                    "job_state": "COMPLETED",
                    "exit_code": {"return_code": 0},
                }
            ]
        }

    state = "UNKNOWN"
    exit_code = 0
    start_time = end_time = 0
    node_list = ""
    reason = ""
    for field in result.split():
        if field.startswith("JobState="):
            state = field.split("=", 1)[1]
        elif field.startswith("ExitCode="):
            exit_code = int(field.split("=", 1)[1].split(":")[0])
        elif field.startswith("NodeList="):
            node_list = field.split("=", 1)[1]
        elif field.startswith("Reason="):
            reason = field.split("=", 1)[1]
        elif field.startswith("StartTime="):
            val = field.split("=", 1)[1]
            if val != "Unknown":
                try:
                    start_time = int(
                        subprocess.run(
                            ["date", "-d", val, "+%s"],
                            capture_output=True,
                            text=True,
                        ).stdout.strip()
                    )
                except Exception:
                    pass
        elif field.startswith("EndTime="):
            val = field.split("=", 1)[1]
            if val != "Unknown":
                try:
                    end_time = int(
                        subprocess.run(
                            ["date", "-d", val, "+%s"],
                            capture_output=True,
                            text=True,
                        ).stdout.strip()
                    )
                except Exception:
                    pass

    return {
        "jobs": [
            {
                "job_id": job_id,
                "job_state": state,
                "exit_code": {"return_code": exit_code},
                "start_time": start_time,
                "end_time": end_time,
                "node_list": node_list,
                "reason": reason,
            }
        ]
    }


@app.delete("/slurm/v0.0.38/job/{job_id}")
async def cancel_job(
    job_id: int, x_slurm_user_token: str | None = Header(None)
):
    check_auth(x_slurm_user_token)
    await run_cmd(["scancel", str(job_id)])
    logger.info("Job cancelled: %d", job_id)
    return {"cancelled": True, "job_id": job_id}


@app.get("/slurm/v0.0.37/job/{job_id}/output")
@app.get("/slurm/v0.0.38/job/{job_id}/output")
async def get_job_output(
    job_id: int, x_slurm_user_token: str | None = Header(None)
):
    check_auth(x_slurm_user_token)
    stdout = stderr = ""

    stdout_path = f"{OUTPUT_DIR}/slurm-{job_id}.out"
    try:
        with open(stdout_path) as f:
            stdout = f.read(MAX_OUTPUT_SIZE)
    except FileNotFoundError:
        pass

    stderr_path = f"{OUTPUT_DIR}/slurm-{job_id}.err"
    try:
        with open(stderr_path) as f:
            stderr = f.read(MAX_OUTPUT_SIZE)
    except FileNotFoundError:
        pass

    return {"output": stdout, "error_output": stderr}


@app.get("/slurm/v0.0.37/nodes")
@app.get("/slurm/v0.0.38/nodes")
async def get_nodes(x_slurm_user_token: str | None = Header(None)):
    check_auth(x_slurm_user_token)
    # %C gives "allocated/idle/other/total" CPU breakdown per node
    result = await run_cmd(["sinfo", "--noheader", "-N", "-o", "%N %T %c %C %m"])
    nodes = []
    for line in result.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 5:
            state_raw = parts[1].upper()
            state_list = []
            if "IDLE" in state_raw:
                state_list.append("IDLE")
            elif "MIX" in state_raw:
                state_list.append("MIXED")
            elif "ALLOC" in state_raw:
                state_list.append("ALLOCATED")
            elif "CLOUD" in state_raw:
                state_list.append("CLOUD")
            elif "DOWN" in state_raw:
                state_list.append("DOWN")
            elif "DRAIN" in state_raw:
                state_list.append("DRAINING")
            else:
                state_list.append(state_raw)

            # Parse %C field: "allocated/idle/other/total"
            cpu_parts = parts[3].split("/")
            free_cpus = int(cpu_parts[1]) if len(cpu_parts) >= 2 else 0

            nodes.append(
                {
                    "name": parts[0],
                    "state": state_list,
                    "cpus": int(parts[2]),
                    "free_cpus": free_cpus,
                    "real_memory": int(parts[4]),
                }
            )
    return {"nodes": nodes}


# ---------------------------------------------------------------------------
# Workspace management (for multi-file mode)
# ---------------------------------------------------------------------------


@app.post("/slurm/v0.0.38/workspace")
async def create_workspace(
    request: Request, x_slurm_user_token: str | None = Header(None)
):
    """Create workspace on NFS from files. Called by agent before job submission."""
    check_auth(x_slurm_user_token)
    body = await request.json()

    workspace_id = body.get("workspace_id")
    if not workspace_id:
        raise HTTPException(400, "workspace_id required")
    try:
        uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(400, "workspace_id must be a valid UUID")

    mode = body.get("mode", "multi_file")
    workspace_path = os.path.join(WORKSPACE_BASE_DIR, workspace_id)

    if os.path.exists(workspace_path):
        return {"workspace_path": workspace_path, "reused": True}

    os.makedirs(workspace_path, mode=0o755, exist_ok=True)
    os.chmod(workspace_path, 0o755)

    try:
        if mode == "multi_file":
            files = body.get("files", [])
            if not files:
                raise HTTPException(400, "No files provided")
            for f in files:
                _validate_and_write_file(workspace_path, f["path"], f["content"])
        else:
            raise HTTPException(400, f"Unsupported workspace mode: {mode}")
    except HTTPException:
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(workspace_path, ignore_errors=True)
        logger.error("Workspace creation failed: %s", e)
        raise HTTPException(500, "Workspace creation failed")

    # Chown workspace to container user (nobody:65534) so jobs can write
    for dirpath, dirnames, filenames in os.walk(workspace_path):
        os.chown(dirpath, 65534, 65534)
        for fname in filenames:
            os.chown(os.path.join(dirpath, fname), 65534, 65534)

    # Set up ephemeral workspace quota (fatal if fails — no unquoted writable workspaces)
    proj_id = _setup_workspace_quota(workspace_path, workspace_id)
    if proj_id is None:
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise HTTPException(500, "Failed to set up workspace quota")

    logger.info("Workspace created: %s (%d files)", workspace_id, len(body.get("files", [])))
    return {"workspace_path": workspace_path, "reused": False}


@app.delete("/slurm/v0.0.38/workspace/{workspace_id}")
async def delete_workspace(
    workspace_id: str, x_slurm_user_token: str | None = Header(None)
):
    """Delete a workspace from NFS. Called by agent after job completion."""
    check_auth(x_slurm_user_token)
    try:
        uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID")

    path = os.path.join(WORKSPACE_BASE_DIR, workspace_id)
    if not os.path.exists(path):
        return {"deleted": False}
    shutil.rmtree(path, ignore_errors=True)
    _remove_workspace_quota(workspace_id)
    logger.info("Workspace deleted: %s", workspace_id)
    return {"deleted": True}


@app.get("/slurm/v0.0.38/allowed-images")
async def get_allowed_images(x_slurm_user_token: str | None = Header(None)):
    """Return available Docker image aliases and their Docker Hub references."""
    check_auth(x_slurm_user_token)
    return {"images": DOCKER_IMAGES}


# ---------------------------------------------------------------------------
# Persistent storage management
# ---------------------------------------------------------------------------


@app.post("/slurm/v0.0.38/storage/init")
async def init_storage(
    request: Request, x_slurm_user_token: str | None = Header(None)
):
    """Create per-wallet storage directory on NFS. Idempotent."""
    check_auth(x_slurm_user_token)
    body = await request.json()
    wallet = body.get("wallet_address", "")
    storage_path = _validate_storage_wallet(wallet)

    created = False
    if not os.path.exists(storage_path):
        os.makedirs(storage_path, mode=0o755, exist_ok=True)
        # Proxy runs as root (confirmed: systemd slurm-proxy service).
        # Chown to uid 65534 (nobody) so containers (--user 65534:65534) can write.
        os.chown(storage_path, 65534, 65534)
        created = True
        logger.info("Storage initialized for wallet %s", wallet)

    # Set up ext4 project quota (idempotent, non-fatal on failure)
    _setup_project_quota(storage_path, wallet)

    return {"storage_path": storage_path, "created": created}


def _count_files(storage_path: str, max_depth: int, max_count: int) -> int:
    """Count files in storage directory (bounded by depth and count)."""
    file_count = 0
    base_depth = storage_path.rstrip("/").count("/")
    for dirpath, dirnames, filenames in os.walk(storage_path, followlinks=False):
        current_depth = dirpath.rstrip("/").count("/") - base_depth
        if current_depth >= max_depth:
            dirnames.clear()
            continue
        for fname in filenames:
            if not os.path.islink(os.path.join(dirpath, fname)):
                file_count += 1
        if file_count > max_count:
            break
    return file_count


def _list_files(storage_path: str, max_entries: int, max_depth: int) -> list[dict]:
    """List files in storage directory (bounded, non-blocking when called via to_thread)."""
    files = []
    base_depth = storage_path.rstrip("/").count("/")
    for dirpath, dirnames, filenames in os.walk(storage_path, followlinks=False):
        current_depth = dirpath.rstrip("/").count("/") - base_depth
        if current_depth >= max_depth:
            dirnames.clear()
            continue
        for fname in filenames:
            if len(files) >= max_entries:
                break
            full = os.path.join(dirpath, fname)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, storage_path)
            try:
                stat = os.lstat(full)
                files.append({
                    "path": rel,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except OSError:
                continue
        if len(files) >= max_entries:
            break
    return files


@app.get("/slurm/v0.0.38/storage/{wallet}/usage")
async def get_storage_usage(
    wallet: str, x_slurm_user_token: str | None = Header(None)
):
    """Get storage usage (bytes + file count) for a wallet."""
    check_auth(x_slurm_user_token)
    storage_path = _validate_storage_wallet(wallet)

    if not os.path.exists(storage_path):
        return {"used_bytes": 0, "file_count": 0}

    try:
        result = await asyncio.wait_for(
            run_cmd(["du", "-sb", storage_path]),
            timeout=5.0,
        )
        used_bytes = int(result.strip().split("\t")[0])
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("du failed for %s: %s", wallet, e)
        used_bytes = 0

    file_count = await asyncio.to_thread(_count_files, storage_path, 5, MAX_STORAGE_FILES)

    # Don't count directory overhead when there are no user files
    if file_count == 0:
        used_bytes = 0

    return {"used_bytes": used_bytes, "file_count": file_count}


@app.get("/slurm/v0.0.38/storage/{wallet}/files")
async def list_storage_files(
    wallet: str, x_slurm_user_token: str | None = Header(None)
):
    """List files in a wallet's persistent storage (max depth 5, max 1000 entries)."""
    check_auth(x_slurm_user_token)
    storage_path = _validate_storage_wallet(wallet)

    if not os.path.exists(storage_path):
        return {"files": []}

    files = await asyncio.to_thread(_list_files, storage_path, 1000, 5)

    return {"files": files}


@app.delete("/slurm/v0.0.38/storage/{wallet}/files/{file_path:path}")
async def delete_storage_file(
    wallet: str, file_path: str, x_slurm_user_token: str | None = Header(None)
):
    """Delete a file or directory from a wallet's persistent storage."""
    check_auth(x_slurm_user_token)
    storage_path = _validate_storage_wallet(wallet)

    if not os.path.exists(storage_path):
        raise HTTPException(404, "Storage not found")

    # Reuse workspace path validation pattern for traversal prevention
    if not file_path or file_path.isspace():
        raise HTTPException(400, "File path is required")
    if "\x00" in file_path:
        raise HTTPException(400, "Null bytes in path")
    normalized = os.path.normpath(file_path)
    if normalized == ".":
        raise HTTPException(400, "Cannot delete storage root")
    if normalized.startswith("..") or normalized.startswith("/"):
        raise HTTPException(400, f"Invalid path: {file_path}")
    if normalized.count(os.sep) > 5:
        raise HTTPException(400, f"File path too deep: {file_path}")

    abs_path = os.path.realpath(os.path.join(storage_path, normalized))
    if not abs_path.startswith(os.path.realpath(storage_path) + os.sep):
        raise HTTPException(400, "Path traversal detected")

    if not os.path.exists(abs_path):
        raise HTTPException(404, "File not found")

    # Symlink safety: never follow symlinks — a container could create a
    # symlink pointing to another wallet's storage directory
    if os.path.islink(abs_path):
        await asyncio.to_thread(os.unlink, abs_path)
        logger.info("Removed symlink %s for %s", file_path, wallet)
        return {"deleted": True}

    if os.path.isdir(abs_path):
        await asyncio.to_thread(shutil.rmtree, abs_path, True)
    else:
        await asyncio.to_thread(os.remove, abs_path)

    logger.info("Deleted storage file %s for %s", file_path, wallet)
    return {"deleted": True}


@app.delete("/slurm/v0.0.38/storage/{wallet}")
async def delete_wallet_storage(
    wallet: str, x_slurm_user_token: str | None = Header(None)
):
    """Delete an entire wallet's storage directory. Used for TTL cleanup."""
    check_auth(x_slurm_user_token)
    storage_path = _validate_storage_wallet(wallet)

    if not os.path.exists(storage_path):
        return {"deleted": False}

    shutil.rmtree(storage_path, ignore_errors=True)
    logger.info("Deleted entire storage for wallet %s", wallet)
    return {"deleted": True}


@app.get("/health")
async def health():
    try:
        await run_cmd(["sinfo", "--noheader", "-o", "%P %a %T %D"])
        return {"status": "ok"}
    except Exception:
        return JSONResponse(status_code=500, content={"status": "error"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=6820)
