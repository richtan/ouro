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
) -> str:
    """Generate a wrapper script for Docker execution on the worker."""
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
DOCKER_BUILDKIT=0 docker build -t "$DOCKER_TAG" -f Dockerfile . >/dev/null 2>&1
docker run \\
    {sec_flags} \\
    -v {shlex.quote(workspace_path)}:/workspace:ro \\
    -w /workspace \\
    "$DOCKER_TAG" \\
    {cmd_str}
EXIT_CODE=$?
docker rmi "$DOCKER_TAG" 2>/dev/null || true
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

    return f"""#!/bin/bash
set -euo pipefail
docker pull -q {shlex.quote(image_ref)} >/dev/null 2>&1 || true
docker run \\
    {sec_flags} \\
    -v {shlex.quote(workspace_path)}:/workspace:ro \\
    -w /workspace \\
    {shlex.quote(image_ref)} \\
    {cmd_str}
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

    docker_image = body.get("docker_image")
    dockerfile_content = body.get("dockerfile_content")
    entrypoint_cmd = body.get("entrypoint_cmd")

    if not workspace_path or (not entrypoint and not entrypoint_cmd):
        raise HTTPException(400, "workspace_path and entrypoint (or entrypoint_cmd) required")

    # Write validated dockerfile_content to workspace to prevent naming discrepancy attacks
    if dockerfile_content:
        df_path = os.path.join(workspace_path, "Dockerfile")
        with open(df_path, "w") as f:
            f.write(dockerfile_content)
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


@app.get("/slurm/v0.0.38/allowed-images")
async def get_allowed_images(x_slurm_user_token: str | None = Header(None)):
    """Return available Docker image aliases and their Docker Hub references."""
    check_auth(x_slurm_user_token)
    return {"images": DOCKER_IMAGES}


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
