# ouro-mcp

MCP server for **Ouro** — run verifiable HPC jobs from any AI agent, paid via [x402](https://x402.org) USDC on Base.

No install. No private keys on the server. The calling agent signs its own x402 USDC payment — no secrets are transmitted.

## Quick Start (Cursor / Claude Desktop)

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ouro-compute": {
      "url": "https://mcp.ourocompute.com/mcp"
    }
  }
}
```

Restart Cursor. Ask the agent to run a compute job. It handles x402 payment signing and returns results automatically.

## How It Works

1. You ask your AI agent: *"Run `echo hello world` on the Ouro cluster"*
2. Agent calls `get_payment_requirements` — gets back a price + x402 payment header. The `files` list can include a Dockerfile that defines the environment (supports FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL).
3. Agent signs the USDC payment locally with its x402 library
4. Agent calls `submit_and_pay` with the signed payment — job is created
5. Job runs on the Slurm cluster. Agent gets stdout and stderr.
6. **No private keys leave the calling agent — only the opaque payment signature is transmitted.**

## Available Tools

| Tool | Description |
|---|---|
| **get_job_status** | Poll a job by ID. Returns output when complete. |
| **get_price_quote** | Check pricing without paying. |
| **get_payment_requirements** | Get x402 payment header for signing (step 1 of payment flow). |
| **submit_and_pay** | Submit a job with a pre-signed x402 payment (step 2 of payment flow). |
| **get_api_endpoint** | Get the direct API URL and body schema for programmatic access. |

## Payment Flow

1. Agent calls `get_payment_requirements(script, nodes, time_limit_min)` (or `files=[...]` with a Dockerfile — no separate `image`/`entrypoint` needed) — gets price + `payment_required_header`
2. Agent decodes the header with its x402 library and signs the USDC payment locally
3. Agent calls `submit_and_pay(payment_signature, ...)` with the same job params — job is created
4. Agent calls `get_job_status(job_id)` to poll for results
5. **No private keys are sent to the MCP server — only the opaque payment signature.**

The price from step 1 is valid for ~30 seconds. Complete both steps within that window. If the price expires, `submit_and_pay` returns a 402 error — retry from step 1.

The agent API is also x402-compatible for direct HTTP access without MCP. Use `get_api_endpoint` to discover the URL and expected request format.

## Self-Hosted

```bash
cd mcp-server && pip install -e .
```

| Variable | Required | Description |
|---|---|---|
| `OURO_API_URL` | Yes | Agent API base URL |
| `PUBLIC_URL` | No | Public URL of this server (for payment links) |

```bash
export OURO_API_URL="https://api.ourocompute.com"
ouro-mcp
```

## Dashboard

View live job status, P&L, and cluster health at:
**https://ourocompute.com**

## License

MIT
