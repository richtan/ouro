#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { privateKeyToAccount } from "viem/accounts";
import { createPublicClient, http } from "viem";
import { base } from "viem/chains";
import { wrapFetchWithPaymentFromConfig } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

const WALLET_PRIVATE_KEY = process.env.WALLET_PRIVATE_KEY;
if (!WALLET_PRIVATE_KEY) {
  console.error(
    "Error: WALLET_PRIVATE_KEY environment variable is required.\n" +
      'Set it in your MCP config\'s env section (hex string starting with "0x").',
  );
  process.exit(1);
}
if (!WALLET_PRIVATE_KEY.startsWith("0x")) {
  console.error("Error: WALLET_PRIVATE_KEY must be a hex string starting with 0x");
  process.exit(1);
}

const API_URL = (process.env.OURO_API_URL || "https://api.ourocompute.com").replace(
  /\/$/,
  "",
);

// ---------------------------------------------------------------------------
// Wallet & x402
// ---------------------------------------------------------------------------

const account = privateKeyToAccount(WALLET_PRIVATE_KEY as `0x${string}`);
const walletAddress = account.address;

/** Sign an EIP-191 message for authenticated API requests. */
async function signedQuery(
  action: string,
  ...parts: string[]
): Promise<URLSearchParams> {
  const ts = String(Math.floor(Date.now() / 1000));
  const allParts = [...parts, walletAddress.toLowerCase(), ts];
  const message = `ouro-${action}:${allParts.join(":")}`;
  const signature = await account.signMessage({ message });
  return new URLSearchParams({ wallet: walletAddress, signature, timestamp: ts });
}

const publicClient = createPublicClient({ chain: base, transport: http() });
const signer = toClientEvmSigner(account, publicClient);

const payFetch = wrapFetchWithPaymentFromConfig(fetch, {
  schemes: [{ network: "eip155:8453", client: new ExactEvmScheme(signer) }],
});

const truncAddr = `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`;
console.error(`Ouro MCP server running · wallet: ${truncAddr}`);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function apiFetch(
  path: string,
  opts: RequestInit & { paid?: boolean; timeout?: number } = {},
): Promise<Response> {
  const { paid = false, timeout = 30_000, ...init } = opts;
  const fetchFn = paid ? payFetch : fetch;
  const url = `${API_URL}${path}`;

  try {
    return await fetchFn(url, {
      ...init,
      redirect: "error",
      signal: AbortSignal.timeout(timeout),
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new Error(`Request to ${path} timed out after ${timeout}ms`);
    }
    throw new Error(
      `Cannot reach ${API_URL}. Check internet connection. (${err instanceof Error ? err.message : err})`,
    );
  }
}

function errorText(status: number, body: string): string {
  switch (status) {
    case 403:
      return "Payment verification failed. Check USDC balance on Base.";
    case 422:
      try {
        const parsed = JSON.parse(body);
        return parsed.detail || parsed.message || body;
      } catch {
        return body;
      }
    case 429:
      return "Rate limited or max active jobs reached. Wait and retry.";
    case 503:
      return "Payment facilitator temporarily unavailable. Retry shortly.";
    default:
      return `API returned ${status}: ${body}`;
  }
}

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------

const server = new McpServer(
  { name: "ouro", version: "1.4.1" },
  {
    instructions: `Ouro runs HPC jobs on a Slurm cluster, paid in USDC via x402 on Base.
Payment is automatic — your wallet signs USDC payments locally.

Typical flow:
  1. run_job(script="echo hello") → { job_id, price }
  2. get_job_status(job_id) → waits for completion and returns result

Submission modes:
  - script: single shell script (simplest)
  - files: list of {path, content} objects (multi-file workspace, can include a Dockerfile)

Use get_price_quote to check pricing before committing.
Use get_allowed_images to see available container images.

Prebuilt images (instant): ouro-ubuntu, ouro-python, ouro-nodejs.
Any Docker Hub image works via Dockerfile (e.g., FROM python:3.12-slim).

Use list_storage to view files in your persistent /scratch volume.
Use mount_storage=true in run_job to mount persistent storage into the container at /scratch (read-write).

Storage limits: 1 GB total, max 10,000 files. Exceeding the file limit returns "Disk quota exceeded" errors inside the container.
Use list_storage to check current usage before running storage-heavy jobs.
Use delete_storage_file to free space or reduce file count.`,
  },
);

// ---------------------------------------------------------------------------
// Tool: run_job
// ---------------------------------------------------------------------------

server.tool(
  "run_job",
  "Submit a compute job and pay automatically. Returns job_id when accepted.",
  {
    script: z.string().optional().describe("Shell script to execute (use this OR files)"),
    files: z
      .array(z.object({ path: z.string(), content: z.string() }))
      .optional()
      .describe("Array of {path, content} file objects (can include a Dockerfile)"),
    image: z.string().default("ouro-ubuntu").describe("Container image (default: ouro-ubuntu)"),
    cpus: z.number().int().min(1).max(8).default(1).describe("CPU cores (1-8)"),
    time_limit_min: z.number().int().min(1).default(1).describe("Max runtime in minutes"),
    webhook_url: z.string().url().optional().describe("URL to receive a POST notification when the job completes or fails"),
    mount_storage: z.boolean().default(false).describe("Mount persistent /scratch volume (read-write). Files persist between jobs. Limits: 1 GB, max 10,000 files."),
  },
  async (params) => {
    // Validate: exactly one of script or files
    if (params.script && params.files) {
      return { content: [{ type: "text", text: "Provide either script or files, not both." }] };
    }
    if (!params.script && !params.files) {
      return { content: [{ type: "text", text: "Provide either script or files." }] };
    }

    const body: Record<string, unknown> = {
      cpus: params.cpus,
      time_limit_min: params.time_limit_min,
      image: params.image,
      submitter_address: walletAddress,
    };
    if (params.script) body.script = params.script;
    if (params.files) body.files = params.files;

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (params.webhook_url) body.webhook_url = params.webhook_url;
    if (params.mount_storage) body.mount_storage = true;

    try {
      const res = await apiFetch("/api/compute/submit", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        paid: true,
      });

      const text = await res.text();
      if (!res.ok) {
        return { content: [{ type: "text", text: errorText(res.status, text) }] };
      }

      return { content: [{ type: "text", text }] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: msg }] };
    }
  },
);

// ---------------------------------------------------------------------------
// Polling fallback (used when SSE is unavailable)
// ---------------------------------------------------------------------------

async function pollUntilDone(jobId: string): Promise<{ content: { type: "text"; text: string }[] }> {
  const maxPolls = 780; // 65 min at 5s intervals (matches SSE timeout)
  for (let i = 0; i < maxPolls; i++) {
    try {
      const authParams = await signedQuery("job-view", jobId);
      const res = await apiFetch(`/api/jobs/${jobId}?${authParams}`);
      if (!res.ok) {
        if (res.status === 404) {
          const text = await res.text();
          return { content: [{ type: "text" as const, text: errorText(res.status, text) }] };
        }
        await new Promise((r) => setTimeout(r, 5_000));
        continue;
      }
      const job = await res.json();
      if (job.status === "completed" || job.status === "failed") {
        return { content: [{ type: "text" as const, text: JSON.stringify(job, null, 2) }] };
      }
    } catch {
      // Network error — continue polling
    }
    await new Promise((r) => setTimeout(r, 5_000));
  }
  return { content: [{ type: "text" as const, text: `Job ${jobId} still running after 65 minutes` }] };
}

// ---------------------------------------------------------------------------
// Tool: get_job_status
// ---------------------------------------------------------------------------

server.tool(
  "get_job_status",
  "Check the status of a job. Returns immediately if already done, otherwise waits for completion and returns the final result with output.",
  {
    job_id: z.string().describe("Job ID to check"),
  },
  async (toolParams) => {
    // Step 1: Check current status — job may already be done
    try {
      const authParams = await signedQuery("job-view", toolParams.job_id);
      const statusRes = await apiFetch(`/api/jobs/${toolParams.job_id}?${authParams}`);
      if (!statusRes.ok) {
        const text = await statusRes.text();
        return { content: [{ type: "text", text: errorText(statusRes.status, text) }] };
      }
      const job = await statusRes.json();
      if (job.status === "completed" || job.status === "failed") {
        return { content: [{ type: "text", text: JSON.stringify(job, null, 2) }] };
      }
      console.error(`Job ${toolParams.job_id.slice(0, 8)} is ${job.status}, streaming events...`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: `Status check failed: ${msg}` }] };
    }

    // Step 2: Connect to SSE for live events
    try {
      const sseAuth = await signedQuery("job-events", toolParams.job_id);
      const sseRes = await apiFetch(`/api/jobs/${toolParams.job_id}/events?${sseAuth}`, {
        timeout: 3_900_000, // 65 minutes
      });

      if (!sseRes.ok) {
        console.error(`SSE unavailable (${sseRes.status}), falling back to polling`);
        return await pollUntilDone(toolParams.job_id);
      }

      const reader = sseRes.body?.getReader();
      if (!reader) {
        console.error("SSE stream body unavailable, falling back to polling");
        return await pollUntilDone(toolParams.job_id);
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let terminalMessage: string | null = null;
        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "job" && event.message) {
              const msg = event.message.toLowerCase();
              if (msg.includes("completed") || msg.includes("failed")) {
                terminalMessage = event.message;
                break;
              }
            }
          } catch {
            // Skip malformed SSE lines
          }
        }

        if (terminalMessage) {
          console.error(`Job ${toolParams.job_id.slice(0, 8)}: ${terminalMessage}`);
          try { reader.cancel(); } catch { /* best effort stream cleanup */ }
          const finalAuth = await signedQuery("job-view", toolParams.job_id);
          const finalRes = await apiFetch(`/api/jobs/${toolParams.job_id}?${finalAuth}`);
          const finalText = await finalRes.text();
          return { content: [{ type: "text", text: finalText }] };
        }
      }

      // Stream ended without terminal event — fetch current status
      console.error("SSE stream ended, fetching final status");
      const fbAuth = await signedQuery("job-view", toolParams.job_id);
      const fallbackRes = await apiFetch(`/api/jobs/${toolParams.job_id}?${fbAuth}`);
      const fallbackText = await fallbackRes.text();
      return { content: [{ type: "text", text: fallbackText }] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`SSE error: ${msg}, fetching current status`);
      try {
        const errAuth = await signedQuery("job-view", toolParams.job_id);
        const fallbackRes = await apiFetch(`/api/jobs/${toolParams.job_id}?${errAuth}`);
        const fallbackText = await fallbackRes.text();
        return { content: [{ type: "text", text: fallbackText }] };
      } catch {
        return { content: [{ type: "text", text: `Job status unavailable: ${msg}` }] };
      }
    }
  },
);

// ---------------------------------------------------------------------------
// Tool: get_price_quote
// ---------------------------------------------------------------------------

server.tool(
  "get_price_quote",
  "Get a price quote without paying. Check pricing before committing.",
  {
    cpus: z.number().int().min(1).max(8).default(1).describe("CPU cores"),
    time_limit_min: z.number().int().min(1).default(1).describe("Max runtime in minutes"),
    submission_mode: z
      .string()
      .default("script")
      .describe("Submission mode: script, multi_file"),
  },
  async (params) => {
    try {
      const qs = new URLSearchParams({
        cpus: String(params.cpus),
        time_limit_min: String(params.time_limit_min),
        submission_mode: params.submission_mode,
      });
      const res = await apiFetch(`/api/price?${qs}`);
      const text = await res.text();
      if (!res.ok) {
        return { content: [{ type: "text", text: errorText(res.status, text) }] };
      }
      return { content: [{ type: "text", text }] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: msg }] };
    }
  },
);

// ---------------------------------------------------------------------------
// Tool: get_allowed_images
// ---------------------------------------------------------------------------

server.tool(
  "get_allowed_images",
  "List available container images for compute jobs.",
  {},
  async () => {
    try {
      const res = await apiFetch("/api/capabilities");
      const text = await res.text();
      if (!res.ok) {
        return { content: [{ type: "text", text: errorText(res.status, text) }] };
      }
      return { content: [{ type: "text", text }] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: msg }] };
    }
  },
);

// ---------------------------------------------------------------------------
// Tool: list_storage
// ---------------------------------------------------------------------------

server.tool(
  "list_storage",
  "List files in your persistent storage. Shows quota usage, file count, and file listing. Includes max_files limit.",
  {},
  async () => {
    try {
      const params = await signedQuery("storage-list");
      const res = await apiFetch(`/api/storage?${params}`);
      const text = await res.text();
      if (!res.ok) {
        return { content: [{ type: "text", text: errorText(res.status, text) }] };
      }
      return { content: [{ type: "text", text }] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: msg }] };
    }
  },
);

// ---------------------------------------------------------------------------
// Tool: delete_storage_file
// ---------------------------------------------------------------------------

server.tool(
  "delete_storage_file",
  "Delete a file or directory from your persistent storage.",
  {
    path: z.string().describe("File path relative to /scratch (e.g. 'models/checkpoint.pt')"),
  },
  async (params) => {
    try {
      // Sign EIP-191 message to prove wallet ownership
      const timestamp = String(Math.floor(Date.now() / 1000));
      const message = `ouro-storage-delete:${walletAddress.toLowerCase()}:${params.path}:${timestamp}`;
      const signature = await account.signMessage({ message });

      const qs = new URLSearchParams({
        wallet: walletAddress,
        path: params.path,
        signature,
        timestamp,
      });
      const res = await apiFetch(`/api/storage/files?${qs}`, { method: "DELETE" });
      const text = await res.text();
      if (!res.ok) {
        return { content: [{ type: "text", text: errorText(res.status, text) }] };
      }
      return { content: [{ type: "text", text }] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: msg }] };
    }
  },
);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

const transport = new StdioServerTransport();
await server.connect(transport);
