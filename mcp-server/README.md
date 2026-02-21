# ouro-mcp

MCP server for **Ouro** — run verifiable HPC jobs from any AI agent, paid via [x402](https://x402.org) USDC on Base.

No install. No private keys on the server. Payment happens in your browser with MetaMask.

## Quick Start (Cursor / Claude Desktop)

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ouro-compute": {
      "url": "https://mcp-server-production-3752.up.railway.app/mcp"
    }
  }
}
```

Restart Cursor. Ask the agent to run a compute job. It returns a one-time payment link — open it, connect MetaMask, pay with USDC on Base, and the agent picks up the result automatically.

## How It Works

1. You ask your AI agent: *"Run `echo hello world` on the Ouro cluster"*
2. Agent calls `run_compute_job` — gets back a payment link + price
3. Agent shows you the link. You open it in your browser.
4. Payment page: connect MetaMask, approve USDC payment on Base
5. Job runs on the Slurm cluster. Agent gets stdout, stderr, and an on-chain proof.
6. **Your private key never leaves your browser.**

## Available Tools

| Tool | Description |
|---|---|
| **run_compute_job** | Submit + wait. Returns payment link, then blocks until result. |
| **submit_compute_job** | Fire-and-forget. Returns payment link + session_id. |
| **get_job_status** | Poll a job or session by ID. |
| **get_price_quote** | Check pricing without paying. |

## Self-Hosted

```bash
cd mcp-server && pip install -e .
```

| Variable | Required | Description |
|---|---|---|
| `OURO_API_URL` | Yes | Agent API base URL |
| `PUBLIC_URL` | No | Public URL of this server (for payment links) |

```bash
export OURO_API_URL="https://agent-production-fdde.up.railway.app"
ouro-mcp
```

## Dashboard

View live job status, P&L, and cluster health at:
**https://dashboard-production-80cd.up.railway.app**

## License

MIT
