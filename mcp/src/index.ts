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
  { name: "ouro", version: "1.6.2" },
  {
    instructions: `Ouro runs compute jobs in isolated containers, paid in USDC via x402 on Base.
Payment is automatic — your wallet signs USDC payments locally.

## CRITICAL: Container Constraints
- **NO NETWORK at runtime** — containers run with --network none. You CANNOT pip install, npm install, apt-get, curl, wget, or git clone in your script. All network operations must happen in setup_commands (build time).
- **Mostly read-only filesystem** — writable paths: /workspace (current dir, ephemeral), /tmp (100 MB, ephemeral), /scratch (1 GB, persisted with mount_storage: true). All other paths are read-only.
- **Memory: 1.6 GB per CPU** — jobs exceeding this are killed (OOMKilled).

## How to submit jobs

Call run_job to submit, then get_job_status to get results.
Tip: if you submitted multiple jobs, you can call get_job_status for each one
as parallel tool calls — each blocks independently, so you get all results in
the time of the slowest job instead of waiting sequentially.

### Option 1: Script only (simplest — stdlib only)
Run a shell command directly. No third-party packages available.
  run_job(script="python3 -c \\"print('hello')\\"", image="ouro-python")

### Option 2: Script + files (stdlib only)
Create files in the workspace, then run a shell command that uses them.
  run_job(
    script="python3 main.py",
    files=[{path: "main.py", content: "import json\\nprint(json.dumps({'ok': True}))"}],
    image="ouro-python"
  )

### Option 3: setup_commands (RECOMMENDED for dependencies)
Install packages at build time (WITH network), then run your script (without network).
Build adds ~30s-2min. Set time_limit_min to 3+ when using this.
  run_job(
    script="python3 main.py",
    files=[{path: "main.py", content: "import numpy\\nprint(numpy.random.rand(3))"}],
    image="ouro-python",
    setup_commands=["pip install numpy"],
    time_limit_min=3
  )

### Option 4: Files with Dockerfile (full control)
Include a Dockerfile for custom dependencies. ENTRYPOINT or CMD required.
  run_job(
    files=[
      {path: "main.py", content: "import numpy; print(numpy.random.rand(3))"},
      {path: "Dockerfile", content: "FROM python:3.12-slim\\nRUN pip install numpy\\nENTRYPOINT [\\"python\\", \\"main.py\\"]"}
    ],
    image="python:3.12-slim"
  )

## Decision tree
- No dependencies needed? → Option 1 or 2 (instant start)
- Need pip/npm/apt packages? → Option 3: setup_commands (easiest)
- Need full Dockerfile control (multi-RUN, COPY, ENV)? → Option 4

## Images
Prebuilt (instant start, stdlib only — NO third-party packages pre-installed):
  - ouro-ubuntu: Ubuntu 22.04 — bash, coreutils (no curl, no git)
  - ouro-python: Python 3.12 — stdlib only (no pip packages)
  - ouro-nodejs: Node.js 20 — core runtime only (no npm packages)
Any Docker Hub image works with setup_commands or Dockerfile.

## Common mistakes
- pip install in script → FAILS (no network). Use setup_commands instead.
- curl/wget in script → FAILS (no network). Use setup_commands instead.
- Writing to /usr, /opt, etc. → FAILS (read-only). Write to /workspace or /tmp.
- Forgetting time_limit_min with setup_commands → may timeout. Use 3+ minutes.
- Passing files or setup_commands as a JSON string → FAILS. Pass as a native JSON array, not a stringified one.

## Storage
Use mount_storage=true to mount persistent /scratch volume (1 GB, max 10,000 files).
Use list_storage to check usage, delete_storage_file to free space.

## Pricing
Use get_price_quote to check price before submitting.`,
  },
);

// ---------------------------------------------------------------------------
// setup_commands → Dockerfile generation
// ---------------------------------------------------------------------------

/** Try to parse a JSON string into its value; return the original if it fails. */
function tryParseJson(v: unknown): unknown {
  if (typeof v === "string") {
    try { return JSON.parse(v); } catch { return v; }
  }
  return v;
}

const BASE_IMAGES: Record<string, string> = {
  "ouro-python": "python:3.12-slim",
  "ouro-nodejs": "node:20-slim",
  "ouro-ubuntu": "ubuntu:22.04",
};

// ---------------------------------------------------------------------------
// Tool: run_job
// ---------------------------------------------------------------------------

server.tool(
  "run_job",
  "Submit a compute job. Containers have NO network at runtime — use setup_commands to install packages. Returns job_id.",
  {
    script: z.string().optional().describe(
      "Shell command(s) to execute. Use alone for simple jobs, or combine with files."
    ),
    files: z.preprocess(
      tryParseJson,
      z.array(z.object({ path: z.string(), content: z.string() }))
        .optional()
        .describe(
          "Files to create in the workspace as a JSON array of {path, content} objects. " +
          "MUST be a native array, NOT a JSON string. " +
          "Use with script to run a command, or include a Dockerfile (with ENTRYPOINT/CMD) for custom environments."
        ),
    ),
    setup_commands: z.preprocess(
      tryParseJson,
      z.array(z.string())
        .optional()
        .describe(
          "Shell commands to run during container build (WITH network access) as a JSON array of strings. " +
          "MUST be a native array, NOT a JSON string. " +
          "Use for: pip/npm/apt install, git clone, downloading data, compiling code. " +
          'Example: ["pip install numpy pandas"] or ["apt-get update && apt-get install -y git", ' +
          '"git clone https://github.com/user/repo /opt/repo"]. ' +
          "Cannot be combined with a Dockerfile in files. " +
          "Build adds ~30s-2min — set time_limit_min to 3+ when using this."
        ),
    ),
    image: z.string().default("ouro-ubuntu").describe(
      "Container image. Prebuilt (stdlib only, NO third-party packages): ouro-ubuntu, ouro-python, ouro-nodejs. " +
      "Any Docker Hub image works with setup_commands or Dockerfile."
    ),
    cpus: z.number().int().min(1).max(8).default(1).describe("CPU cores (1-8)"),
    time_limit_min: z.number().int().min(1).max(60).default(1).describe("Max runtime in minutes (1-60)"),
    webhook_url: z.string().url().optional().describe("URL to receive a POST notification when the job completes or fails"),
    mount_storage: z.boolean().default(false).describe("Mount persistent /scratch volume (read-write). Files persist between jobs. Limits: 1 GB, max 10,000 files."),
  },
  async (params) => {
    if (!params.script && !params.files) {
      return { content: [{ type: "text", text: "Provide script, files, or both." }] };
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

    // Handle setup_commands: generate Dockerfile + _run.sh
    if (params.setup_commands?.length) {
      const hasDockerfile = params.files?.some(
        (f) => f.path.toLowerCase() === "dockerfile",
      );
      if (hasDockerfile) {
        return {
          content: [
            {
              type: "text",
              text: "Cannot use both setup_commands and a Dockerfile. Use one or the other.",
            },
          ],
        };
      }

      const dockerImage = BASE_IMAGES[params.image] ?? params.image;
      const files: { path: string; content: string }[] = [
        ...(params.files ?? []),
      ];
      let entrypointFile: string;

      if (params.script) {
        // Write script content to a shell file
        entrypointFile = files.some((f) => f.path === "_run.sh")
          ? "_ouro_entrypoint.sh"
          : "_run.sh";
        let scriptContent = params.script;
        if (scriptContent.trimStart().startsWith("#!")) {
          scriptContent = scriptContent.split("\n").slice(1).join("\n");
        }
        files.push({
          path: entrypointFile,
          content: `#!/bin/bash\nset -euo pipefail\n${scriptContent}`,
        });
      } else {
        // Auto-detect entrypoint from files
        const detectable = files.find((f) =>
          /\.(py|js|sh|rb|r|jl)$/i.test(f.path),
        );
        if (!detectable) {
          return {
            content: [
              {
                type: "text",
                text: "setup_commands without 'script' requires at least one .py, .js, .sh, .rb, .r, or .jl file as entrypoint",
              },
            ],
          };
        }
        entrypointFile = detectable.path;
      }

      // Determine interpreter from file extension
      const ext = entrypointFile.split(".").pop()?.toLowerCase();
      const interpreter: Record<string, string> = {
        sh: "/bin/bash",
        py: "python3",
        js: "node",
        rb: "ruby",
        r: "Rscript",
        jl: "julia",
      };
      const entrypointCmd = [
        interpreter[ext ?? ""] ?? "/bin/bash",
        entrypointFile,
      ];

      // Generate Dockerfile
      const runLines = params.setup_commands
        .map((c) => c.replace(/[\r\n]+/g, " ").trim())
        .filter((c) => c.length > 0)
        .map((c) => `RUN ${c}`);

      const dockerfile = [
        `FROM ${dockerImage}`,
        ...runLines,
        `ENTRYPOINT ${JSON.stringify(entrypointCmd)}`,
      ].join("\n");

      files.push({ path: "Dockerfile", content: dockerfile });

      // Override body for API submission
      body.files = files;
      body.image = dockerImage;
      delete body.script;
    }

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
