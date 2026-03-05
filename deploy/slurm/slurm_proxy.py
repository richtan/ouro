"""Slurm REST proxy — wraps real sbatch/scontrol/sinfo with Apptainer isolation.

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
import tempfile
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_ALLOWED_CWD = {"/tmp"}
MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DEF_SIZE = 64 * 1024  # 64KB max .def content
MAX_IMAGE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB max built image
IMAGE_BUILD_TIMEOUT = 180  # seconds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slurm_proxy")

JWT_TOKEN = os.environ.get("SLURM_PROXY_TOKEN", "")
if not JWT_TOKEN:
    raise SystemExit("SLURM_PROXY_TOKEN is empty — refusing to start without auth token")

app = FastAPI(title="Ouro Slurm Proxy")

OUTPUT_DIR = "/ouro-jobs/output"
SCRIPTS_DIR = "/ouro-jobs/scripts"
WORKSPACE_BASE_DIR = "/ouro-jobs/workspaces"
IMAGES_DIR = "/ouro-jobs/images"
CUSTOM_IMAGES_DIR = "/ouro-jobs/images/custom"
BASE_IMAGE = "/ouro-jobs/images/base.sif"
APPTAINER_AVAILABLE = os.path.exists("/usr/bin/apptainer") or os.path.exists("/usr/local/bin/apptainer")

# Locks for concurrent image builds (keyed by def hash)
_build_locks: dict[str, asyncio.Lock] = {}

ALLOWED_IMAGES = {
    "base":      "base.sif",
    "python312": "python312.sif",
    "node20":    "node20.sif",
    "pytorch":   "pytorch.sif",
    "r-base":    "r-base.sif",
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


def resolve_image(name: str | None) -> str:
    """Map image name to .sif path. Validates against allowlist and checks file exists."""
    if not name or name == "base":
        if not os.path.exists(BASE_IMAGE):
            raise HTTPException(503, "Base container image missing")
        return BASE_IMAGE
    sif_file = ALLOWED_IMAGES.get(name)
    if not sif_file:
        raise HTTPException(400, f"Unknown image: {name}. Allowed: {', '.join(sorted(ALLOWED_IMAGES))}")
    path = os.path.join(IMAGES_DIR, sif_file)
    if not os.path.exists(path):
        raise HTTPException(503, f"Container image '{name}' not available on this cluster")
    return path


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
    if not abs_path.startswith(os.path.realpath(workspace_path)):
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


def wrap_in_apptainer(
    workspace_path: str,
    entrypoint: str,
    job_name: str,
    image_name: str | None = None,
    sif_path: str | None = None,
    entrypoint_cmd: list[str] | None = None,
) -> str:
    """Wrap workspace execution in Apptainer container.

    Returns wrapper script string. Workspace is bind-mounted read-only at /workspace.

    Args:
        sif_path: Direct path to .sif image (from Dockerfile build). Takes priority over image_name.
        entrypoint_cmd: Exec-form command from Dockerfile (e.g. ["python", "main.py"]).
            When set, --pwd /workspace is added so relative paths resolve to workspace files.
            Falls back to extension-based inference from entrypoint when not set.
    """
    if not APPTAINER_AVAILABLE:
        raise HTTPException(503, "Container isolation unavailable (Apptainer missing)")

    image_path = sif_path or resolve_image(image_name)

    if entrypoint_cmd:
        # Dockerfile-based: use explicit command with --pwd /workspace
        cmd_str = " ".join(shlex.quote(part) for part in entrypoint_cmd)
        return f"""#!/bin/bash
set -euo pipefail
ulimit -u 4096
apptainer exec \\
    --contain --cleanenv --writable-tmpfs --no-home \\
    --net --network none \\
    --pwd /workspace \\
    --bind {shlex.quote(workspace_path)}:/workspace:ro \\
    {shlex.quote(image_path)} \\
    {cmd_str}
exit $?
"""

    # Legacy path: infer executor from entrypoint file extension
    normalized = os.path.normpath(entrypoint)
    if normalized.startswith("..") or normalized.startswith("/") or "\x00" in entrypoint:
        raise HTTPException(400, "Invalid entrypoint path")

    ext = os.path.splitext(normalized)[1].lower()
    executor = {".py": "python3", ".r": "Rscript", ".jl": "julia"}.get(ext, "bash")

    return f"""#!/bin/bash
set -euo pipefail
ulimit -u 4096
apptainer exec \\
    --contain --cleanenv --writable-tmpfs --no-home \\
    --net --network none \\
    --bind {shlex.quote(workspace_path)}:/workspace:ro \\
    {shlex.quote(image_path)} \\
    {executor} {shlex.quote(f'/workspace/{normalized}')}
exit $?
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
        entrypoint = "job.sh"

    sif_path = body.get("sif_path")
    entrypoint_cmd = body.get("entrypoint_cmd")

    if not workspace_path or (not entrypoint and not entrypoint_cmd):
        raise HTTPException(400, "workspace_path and entrypoint (or entrypoint_cmd) required")

    wrapper_script = wrap_in_apptainer(
        workspace_path, entrypoint or "", name, image_name,
        sif_path=sif_path, entrypoint_cmd=entrypoint_cmd,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, dir="/tmp"
    ) as f:
        f.write(wrapper_script)
        wrapper_path = f.name
    os.chmod(wrapper_path, 0o755)

    logger.info(
        "Submitting: partition=%s name=%s cpus=%s time=%s isolation=apptainer",
        partition, name, cpus, time_limit,
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
                f"--time={time_limit}",
                f"--output={OUTPUT_DIR}/slurm-%j.out",
                f"--error={OUTPUT_DIR}/slurm-%j.err",
                f"--chdir={cwd}",
                wrapper_path,
            ]
        )
        job_id = int(result.strip())
        logger.info("Job submitted: %d (isolation: apptainer)", job_id)
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
    for field in result.split():
        if field.startswith("JobState="):
            state = field.split("=", 1)[1]
        elif field.startswith("ExitCode="):
            exit_code = int(field.split("=", 1)[1].split(":")[0])
        elif field.startswith("NodeList="):
            node_list = field.split("=", 1)[1]
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
            }
        ]
    }


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

    output_hash = hashlib.sha256((stdout + stderr).encode()).hexdigest()
    return {"output": stdout, "error_output": stderr, "output_hash": output_hash}


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
    logger.info("Workspace deleted: %s", workspace_id)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Image build (for custom Dockerfiles converted to .def)
# ---------------------------------------------------------------------------


@app.post("/slurm/v0.0.38/image/build")
async def build_image(
    request: Request, x_slurm_user_token: str | None = Header(None)
):
    """Build an Apptainer image from a .def file. Caches by content hash."""
    check_auth(x_slurm_user_token)

    if not APPTAINER_AVAILABLE:
        raise HTTPException(503, "Apptainer not available")

    body = await request.json()
    def_content = body.get("def_content")
    if not def_content:
        raise HTTPException(400, "def_content required")

    if len(def_content.encode()) > MAX_DEF_SIZE:
        raise HTTPException(400, f"Definition file too large (max {MAX_DEF_SIZE // 1024}KB)")

    def_hash = hashlib.sha256(def_content.encode()).hexdigest()
    final_path = os.path.join(CUSTOM_IMAGES_DIR, f"{def_hash}.sif")

    # Fast path: already cached
    if os.path.exists(final_path):
        return {"sif_path": final_path, "cached": True, "build_time_s": 0.0}

    # Acquire per-hash lock to prevent duplicate builds
    if def_hash not in _build_locks:
        _build_locks[def_hash] = asyncio.Lock()
    lock = _build_locks[def_hash]

    async with lock:
        # Double-check after acquiring lock
        if os.path.exists(final_path):
            return {"sif_path": final_path, "cached": True, "build_time_s": 0.0}

        # Write .def to temp file
        os.makedirs(CUSTOM_IMAGES_DIR, exist_ok=True)
        temp_def = os.path.join("/tmp", f"{uuid.uuid4().hex}.def")
        temp_sif = os.path.join("/tmp", f"{uuid.uuid4().hex}.sif")

        try:
            with open(temp_def, "w") as f:
                f.write(def_content)

            logger.info("Building image: %s.sif from .def (%d bytes)", def_hash, len(def_content))
            import time
            start = time.monotonic()

            proc = await asyncio.create_subprocess_exec(
                "sudo", "apptainer", "build", "--notest", temp_sif, temp_def,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=IMAGE_BUILD_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                raise HTTPException(504, f"Image build timed out ({IMAGE_BUILD_TIMEOUT}s limit)")

            elapsed = time.monotonic() - start

            if proc.returncode != 0:
                raw_log = stderr.decode()[-2000:]  # Last 2KB of build log
                logger.error("Image build failed (rc=%d): %s", proc.returncode, raw_log[:500])
                # V9: Sanitize build logs to avoid leaking system paths
                sanitized_log = re.sub(r"/(?:usr|etc|var|tmp|home|root|ouro-jobs)/\S+", "<path>", raw_log)[-500:]
                return JSONResponse(
                    status_code=502,
                    content={"error": "Build failed", "build_log": sanitized_log},
                )

            # Check built image size before moving to cache
            image_size = os.path.getsize(temp_sif)
            if image_size > MAX_IMAGE_SIZE:
                os.unlink(temp_sif)
                raise HTTPException(400, f"Built image too large ({image_size // (1024*1024)}MB, max {MAX_IMAGE_SIZE // (1024*1024*1024)}GB)")

            # Atomic move to final path
            os.rename(temp_sif, final_path)
            logger.info("Image built: %s.sif in %.1fs (%dMB)", def_hash, elapsed, image_size // (1024*1024))

            return {"sif_path": final_path, "cached": False, "build_time_s": round(elapsed, 1)}

        finally:
            # Clean up temp files
            for p in (temp_def, temp_sif):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass


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
