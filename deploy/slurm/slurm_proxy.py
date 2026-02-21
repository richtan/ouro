"""Slurm REST proxy — wraps real sbatch/scontrol/sinfo with Apptainer isolation.

Maintains the same API the Ouro agent expects (slurmrestd v0.0.38 compatible)
so the agent's SlurmClient needs zero changes.
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import tempfile

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slurm_proxy")

app = FastAPI(title="Ouro Slurm Proxy")

JWT_TOKEN = os.environ.get("SLURM_PROXY_TOKEN", "")
OUTPUT_DIR = "/ouro-jobs/output"
SCRIPTS_DIR = "/ouro-jobs/scripts"
BASE_IMAGE = "/ouro-jobs/images/base.sif"
APPTAINER_AVAILABLE = os.path.exists("/usr/bin/apptainer") or os.path.exists("/usr/local/bin/apptainer")


def check_auth(token: str | None):
    if JWT_TOKEN and token != JWT_TOKEN:
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
        raise HTTPException(500, f"Command failed: {err_msg}")
    return stdout.decode()


def parse_time_limit(tl) -> str:
    if isinstance(tl, dict):
        seconds = tl.get("number", 300)
        minutes = max(1, seconds // 60)
        return str(minutes)
    return str(tl)


def wrap_in_apptainer(user_script: str, job_name: str) -> str:
    """Wrap user script in Apptainer container for isolation."""
    if not APPTAINER_AVAILABLE or not os.path.exists(BASE_IMAGE):
        logger.warning("Apptainer or base image not available, running without isolation")
        return user_script

    escaped = user_script.replace("'", "'\\''")

    return f"""#!/bin/bash
mkdir -p {SCRIPTS_DIR}
SCRIPT_FILE={SCRIPTS_DIR}/{job_name}-$SLURM_JOB_ID.sh

cat > "$SCRIPT_FILE" << 'OURO_SCRIPT_END'
{user_script}
OURO_SCRIPT_END
chmod +x "$SCRIPT_FILE"

apptainer exec \\
    --contain --writable-tmpfs --no-home \\
    --bind "$SCRIPT_FILE":/job.sh:ro \\
    {BASE_IMAGE} \\
    bash /job.sh
EXIT_CODE=$?

rm -f "$SCRIPT_FILE"
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

    script = body.get("script", "#!/bin/bash\necho hello")
    if not script.startswith("#!"):
        script = "#!/bin/bash\n" + script

    job = body.get("job", {})
    partition = "compute"
    name = job.get("name", "ouro-job")
    nodes = str(job.get("nodes", "1"))
    time_limit = parse_time_limit(job.get("time_limit", "5"))
    cwd = job.get("current_working_directory", "/tmp")

    wrapped = wrap_in_apptainer(script, name)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, dir="/tmp"
    ) as f:
        f.write(wrapped)
        script_path = f.name
    os.chmod(script_path, 0o755)

    isolation_mode = "apptainer" if APPTAINER_AVAILABLE and os.path.exists(BASE_IMAGE) else "bare"
    logger.info(
        "Submitting: partition=%s name=%s nodes=%s time=%s isolation=%s",
        partition, name, nodes, time_limit, isolation_mode,
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
                script_path,
            ]
        )
        job_id = int(result.strip())
        logger.info("Job submitted: %d (isolation: %s)", job_id, isolation_mode)
        return {"job_id": job_id, "step_id": "batch", "error_code": 0, "error": ""}
    except Exception as e:
        logger.error("Submit failed: %s", e)
        raise
    finally:
        try:
            os.unlink(script_path)
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
        stderr_path = f"{base_dir}/slurm-{job_id}.err"
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


@app.get("/health")
async def health():
    try:
        result = await run_cmd(["sinfo", "--noheader", "-o", "%P %a %T %D"])
        return {"status": "ok", "cluster": "ouro", "sinfo": result.strip()}
    except Exception as e:
        return JSONResponse(500, {"status": "error", "detail": str(e)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=6820)
