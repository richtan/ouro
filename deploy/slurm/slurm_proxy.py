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
import shutil
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slurm_proxy")

JWT_TOKEN = os.environ.get("SLURM_PROXY_TOKEN", "")
if not JWT_TOKEN:
    logger.critical("SLURM_PROXY_TOKEN is empty — all endpoints will reject requests")

app = FastAPI(title="Ouro Slurm Proxy")

OUTPUT_DIR = "/ouro-jobs/output"
SCRIPTS_DIR = "/ouro-jobs/scripts"
WORKSPACE_BASE_DIR = "/ouro-jobs/workspaces"
IMAGES_DIR = "/ouro-jobs/images"
BASE_IMAGE = "/ouro-jobs/images/base.sif"
APPTAINER_AVAILABLE = os.path.exists("/usr/bin/apptainer") or os.path.exists("/usr/local/bin/apptainer")

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
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w") as f:
        f.write(content)


def wrap_in_apptainer(user_script: str, job_name: str, image_name: str | None = None) -> tuple[str, str]:
    """Wrap user script in Apptainer container for isolation.

    Returns (wrapper_script, user_script_path) tuple.  The caller must
    clean up *both* temp files.

    Raises HTTPException(503) if Apptainer or the container image is missing —
    we must never fall back to running user code on the bare host.
    """
    if not APPTAINER_AVAILABLE:
        raise HTTPException(503, "Container isolation unavailable (Apptainer missing)")

    image_path = resolve_image(image_name)

    # Write user script to a temp file via Python — avoids heredoc injection
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, dir=SCRIPTS_DIR, prefix=f"{job_name}-",
    ) as uf:
        uf.write(user_script)
        user_script_path = uf.name
    os.chmod(user_script_path, 0o755)

    wrapper = f"""#!/bin/bash
apptainer exec \\
    --contain --writable-tmpfs --no-home \\
    --bind "{user_script_path}":/job.sh:ro \\
    --env HOME=/tmp \\
    {image_path} \\
    bash /job.sh
exit $?
"""
    return wrapper, user_script_path


def wrap_in_apptainer_workspace(
    workspace_path: str, entrypoint: str, job_name: str, image_name: str | None = None
) -> str:
    """Wrap a multi-file workspace execution in Apptainer container.

    Returns wrapper script string. Workspace is bind-mounted read-only at /workspace.
    """
    if not APPTAINER_AVAILABLE:
        raise HTTPException(503, "Container isolation unavailable (Apptainer missing)")

    image_path = resolve_image(image_name)

    normalized = os.path.normpath(entrypoint)
    if normalized.startswith("..") or normalized.startswith("/") or "\x00" in entrypoint:
        raise HTTPException(400, "Invalid entrypoint path")

    ext = os.path.splitext(normalized)[1].lower()
    executor = {".py": "python3", ".r": "Rscript", ".jl": "julia"}.get(ext, "bash")

    return f"""#!/bin/bash
set -euo pipefail
apptainer exec \\
    --contain --writable-tmpfs --no-home \\
    --bind "{workspace_path}":/workspace:ro \\
    --env HOME=/tmp \\
    {image_path} \\
    {executor} /workspace/{normalized}
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

    submission_mode = body.get("submission_mode", "script")
    image_name = body.get("image")

    job = body.get("job", {})
    partition = "compute"
    name = job.get("name", "ouro-job")
    nodes = str(job.get("nodes", "1"))
    time_limit = parse_time_limit(job.get("time_limit", "5"))
    cwd = job.get("current_working_directory", "/tmp")

    cleanup_paths = []

    if submission_mode == "multi_file":
        workspace_path = body.get("workspace_path")
        entrypoint = body.get("entrypoint")
        if not workspace_path or not entrypoint:
            raise HTTPException(400, "workspace_path and entrypoint required for multi_file mode")
        wrapper_script = wrap_in_apptainer_workspace(workspace_path, entrypoint, name, image_name)
    else:
        # Default script mode
        script = body.get("script", "#!/bin/bash\necho hello")
        if not script.startswith("#!"):
            script = "#!/bin/bash\n" + script
        wrapper_script, user_script_path = wrap_in_apptainer(script, name, image_name)
        cleanup_paths.append(user_script_path)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, dir="/tmp"
    ) as f:
        f.write(wrapper_script)
        wrapper_path = f.name
    os.chmod(wrapper_path, 0o755)
    cleanup_paths.append(wrapper_path)

    logger.info(
        "Submitting: partition=%s name=%s nodes=%s time=%s mode=%s isolation=apptainer",
        partition, name, nodes, time_limit, submission_mode,
    )

    try:
        result = await run_cmd(
            [
                "sbatch",
                "--parsable",
                f"--partition={partition}",
                f"--job-name={name}",
                f"--nodes={nodes}",
                f"--time={time_limit}",
                f"--output={OUTPUT_DIR}/slurm-%j.out",
                f"--error={OUTPUT_DIR}/slurm-%j.err",
                f"--chdir={cwd}",
                wrapper_path,
            ]
        )
        job_id = int(result.strip())
        logger.info("Job submitted: %d (mode=%s, isolation: apptainer)", job_id, submission_mode)
        return {"job_id": job_id, "step_id": "batch", "error_code": 0, "error": ""}
    except Exception as e:
        logger.error("Submit failed: %s", e)
        raise
    finally:
        for path in cleanup_paths:
            try:
                os.unlink(path)
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

    for base_dir in [OUTPUT_DIR, "/tmp"]:
        stdout_path = f"{base_dir}/slurm-{job_id}.out"
        try:
            with open(stdout_path) as f:
                stdout = f.read()
            break
        except FileNotFoundError:
            continue

    for base_dir in [OUTPUT_DIR, "/tmp"]:
        stderr_path = f"{base_dir}/slurm-{job_id}.err"
        try:
            with open(stderr_path) as f:
                stderr = f.read()
            break
        except FileNotFoundError:
            continue

    output_hash = hashlib.sha256((stdout + stderr).encode()).hexdigest()
    return {"output": stdout, "error_output": stderr, "output_hash": output_hash}


@app.get("/slurm/v0.0.37/nodes")
@app.get("/slurm/v0.0.38/nodes")
async def get_nodes(x_slurm_user_token: str | None = Header(None)):
    check_auth(x_slurm_user_token)
    result = await run_cmd(["sinfo", "--noheader", "-N", "-o", "%N %T %c %m"])
    nodes = []
    for line in result.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 4:
            state_raw = parts[1].upper()
            state_list = []
            if "IDLE" in state_raw:
                state_list.append("IDLE")
            elif "ALLOC" in state_raw:
                state_list.append("ALLOCATED")
            elif "MIX" in state_raw:
                state_list.append("ALLOCATED")
            elif "DOWN" in state_raw:
                state_list.append("DOWN")
            else:
                state_list.append(state_raw)

            nodes.append(
                {
                    "name": parts[0],
                    "state": state_list,
                    "cpus": int(parts[2]),
                    "real_memory": int(parts[3]),
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

    os.makedirs(workspace_path, exist_ok=True)

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
