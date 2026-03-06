# ouro-sdk

Python SDK for submitting and managing compute jobs on Ouro.

## Install

```bash
pip install ./ouro-sdk    # from the project root
# or
cd ouro-sdk && pip install -e .
```

## Quick Start

```python
from ouro_sdk import OuroClient

async with OuroClient() as ouro:
    quote = await ouro.quote(cpus=2, time_limit_min=5)
    print(f"Price: {quote.price}")

    job_id = await ouro.submit("python3 train.py", cpus=2, time_limit_min=5)
    result = await ouro.wait(job_id)
    print(result.status, result.output)
```

### Multi-file jobs with Dockerfile

```python
from ouro_sdk import OuroClient

async with OuroClient() as ouro:
    job_id = await ouro.submit(
        files=[
            {"path": "Dockerfile", "content": (
                "FROM python:3.12-slim\n"
                "WORKDIR /app\n"
                "COPY requirements.txt .\n"
                "RUN pip install -r requirements.txt\n"
                "COPY train.py .\n"
                "ENTRYPOINT [\"python3\", \"train.py\"]\n"
            )},
            {"path": "requirements.txt", "content": "numpy\nscipy\n"},
            {"path": "train.py", "content": "import numpy; print('done')"},
        ],
        cpus=2,
        time_limit_min=5,
    )
    result = await ouro.wait(job_id)
    print(result.output)
```

Supported Dockerfile instructions: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL. COPY/ADD accept local workspace paths only (no globs, no URLs). USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD are rejected.

### Service discovery

```python
from ouro_sdk import OuroClient

async with OuroClient() as ouro:
    caps = await ouro.capabilities()
    print(caps["payment"]["protocol"])  # "x402"
    print(caps["trust"]["on_chain_proofs"])
```

## API

- `OuroClient(api_url, client, poll_interval_s, poll_timeout_s)` — constructor
- `quote(cpus, time_limit_min)` — get a price quote
- `submit(script, cpus, time_limit_min, submitter_address)` — submit a job (returns job_id)
- `get_job(job_id)` — fetch job status
- `wait(job_id)` — poll until complete/failed
- `run(script, ...)` — submit + wait in one call
- `capabilities()` — fetch server capability manifest
