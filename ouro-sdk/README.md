# ouro-sdk

Python SDK for submitting and managing compute jobs on Ouro.

## Install

```bash
pip install ouro-sdk
```

## Quick Start

```python
from ouro_sdk import OuroClient

async with OuroClient() as ouro:
    quote = await ouro.quote(nodes=2, time_limit_min=5)
    print(f"Price: {quote.price}")

    job_id = await ouro.submit("python3 train.py", nodes=2, time_limit_min=5)
    result = await ouro.wait(job_id)
    print(result.status, result.output)
```

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
- `quote(nodes, time_limit_min)` — get a price quote
- `submit(script, nodes, time_limit_min, submitter_address)` — submit a job (returns job_id)
- `get_job(job_id)` — fetch job status
- `wait(job_id)` — poll until complete/failed
- `run(script, ...)` — submit + wait in one call
- `capabilities()` — fetch server capability manifest
