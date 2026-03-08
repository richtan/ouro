import CodeBlock from "@/components/docs/CodeBlock";
import EndpointCard from "@/components/docs/EndpointCard";
import ParamTable from "@/components/docs/ParamTable";
import StepCard from "@/components/docs/StepCard";

const CURL_402_CMD = `curl -X POST https://api.ourocompute.com/api/compute/submit \\
  -H "Content-Type: application/json" \\
  -d '{"script": "echo hello", "cpus": 1, "time_limit_min": 1}'`;

const CURL_402 = `${CURL_402_CMD}

# Response: 402 Payment Required
# Headers: payment-required: eyJ0eXAiOiJ4NDAyL...
# Body: { "price": "$0.0841", "breakdown": { ... } }`;

const CURL_SUBMIT_CMD = `curl -X POST https://api.ourocompute.com/api/compute/submit \\
  -H "Content-Type: application/json" \\
  -H "payment-signature: <your-signed-x402-payment>" \\
  -d '{"script": "echo hello", "cpus": 1, "time_limit_min": 1}'`;

const CURL_SUBMIT = `${CURL_SUBMIT_CMD}

# Response: 200 OK
# Body: { "job_id": "a1b2c3d4-...", "status": "pending", "price": "$0.0841" }`;

const CURL_MULTIFILE_CMD = `curl -X POST https://api.ourocompute.com/api/compute/submit \\
  -H "Content-Type: application/json" \\
  -H "payment-signature: <your-signed-x402-payment>" \\
  -d '{
    "files": [
      {"path": "main.py", "content": "from utils import greet\\ngreet()"},
      {"path": "utils.py", "content": "def greet():\\n    print(\\"hello\\")"}
    ],
    "entrypoint": "python main.py",
    "image": "ouro-python",
    "cpus": 1,
    "time_limit_min": 5
  }'`;

const CURL_MULTIFILE = `${CURL_MULTIFILE_CMD}

# Response: 200 OK
# Body: { "job_id": "e5f6g7h8-...", "status": "pending", "price": "$0.0841" }`;

const CURL_STATUS_CMD = `curl https://api.ourocompute.com/api/jobs/{job_id}`;

const CURL_STATUS = `${CURL_STATUS_CMD}

# Response: 200 OK
# Body: { "id": "...", "status": "completed", "output": "hello\\n", ... }`;

export default function ApiPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          REST API
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Direct HTTP endpoints with x402 payment protocol.
        </p>
      </div>

      {/* Base URL */}
      <section className="mb-10">
        <div className="bg-o-surface border border-o-border rounded-xl px-4 py-3.5">
          <span className="text-xs text-o-muted uppercase tracking-wider">Base URL</span>
          <p className="font-mono text-sm text-o-blueText mt-1">
            https://api.ourocompute.com
          </p>
        </div>
      </section>

      {/* x402 flow */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          x402 Payment Flow
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-6">
          Ouro uses the x402 payment protocol. POST without payment to get the price,
          sign the payment locally, then POST again with the signature.
        </p>

        <div className="mb-6">
          <StepCard number={1} title="Get price (402 response)">
            <CodeBlock filename="terminal" language="bash" copyText={CURL_402_CMD}>
              {CURL_402}
            </CodeBlock>
          </StepCard>
          <StepCard number={2} title="Sign and submit (script mode)">
            <CodeBlock filename="terminal" language="bash" copyText={CURL_SUBMIT_CMD}>
              {CURL_SUBMIT}
            </CodeBlock>
            <div className="mt-4">
              <p className="text-xs text-o-muted uppercase tracking-wider mb-2">Or use multi-file mode</p>
              <CodeBlock filename="terminal" language="bash" copyText={CURL_MULTIFILE_CMD}>
                {CURL_MULTIFILE}
              </CodeBlock>
            </div>
          </StepCard>
          <StepCard number={3} title="Poll for results" last>
            <CodeBlock filename="terminal" language="bash" copyText={CURL_STATUS_CMD}>
              {CURL_STATUS}
            </CodeBlock>
          </StepCard>
        </div>
      </section>

      {/* Endpoints */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">
          Endpoints
        </h2>
        <div className="space-y-3">
          <EndpointCard
            method="POST"
            path="/api/compute/submit"
            auth="x402"
            description="Submit a compute job (script or multi-file mode)"
          >
            <p className="text-xs text-o-textSecondary mb-4">
              Supports two submission modes: <strong className="text-o-text">script mode</strong> (single shell script string)
              and <strong className="text-o-text">multi-file mode</strong> (array of files with an entrypoint command).
              Provide either <code className="text-o-blueText">script</code> or <code className="text-o-blueText">files</code> + <code className="text-o-blueText">entrypoint</code>.
            </p>
            <h4 className="text-xs text-o-muted uppercase tracking-wider mb-3">Request Body</h4>
            <ParamTable
              params={[
                { name: "script", type: "string", description: "Shell script to execute (script mode)" },
                { name: "files", type: "array", description: 'Array of {path, content} objects written to a workspace (multi-file mode)' },
                { name: "entrypoint", type: "string", description: 'Command to run inside the workspace, e.g. "python main.py" (multi-file mode)' },
                { name: "image", type: "string", description: "Container image: ouro-ubuntu, ouro-python, ouro-nodejs (default: ouro-ubuntu)" },
                { name: "cpus", type: "int", description: "Number of CPU cores (default 1, max 8)" },
                { name: "time_limit_min", type: "int", description: "Max runtime in minutes (default 1)" },
                { name: "submitter_address", type: "string", description: "Your wallet address for tracking" },
              ]}
            />
            <h4 className="text-xs text-o-muted uppercase tracking-wider mt-4 mb-3">Headers</h4>
            <ParamTable
              params={[
                { name: "payment-signature", type: "string", description: "Signed x402 payment (omit for price quote)" },
                { name: "X-BUILDER-CODE", type: "string", description: "Builder code for ERC-8021 attribution (optional)" },
              ]}
            />
          </EndpointCard>

          <EndpointCard
            method="GET"
            path="/api/price"
            description="Get a price quote without submitting a job"
          >
            <h4 className="text-xs text-o-muted uppercase tracking-wider mb-3">Query Parameters</h4>
            <ParamTable
              params={[
                { name: "cpus", type: "int", description: "Number of CPU cores (default 1, max 8)" },
                { name: "time_limit_min", type: "int", description: "Max runtime in minutes (default 1)" },
                { name: "submission_mode", type: "string", description: "Submission mode: script, multi_file, archive, or git (default: script)" },
              ]}
            />
            <p className="text-xs text-o-textSecondary mt-3">
              Returns <code className="text-o-blueText">price</code> (formatted string) and <code className="text-o-blueText">breakdown</code> (gas, LLM, compute cost components). Public endpoint, no authentication required.
            </p>
          </EndpointCard>

          <EndpointCard
            method="POST"
            path="/api/compute/submit/from-session"
            auth="x402"
            description="Submit a job from a payment session"
          >
            <p className="text-xs text-o-textSecondary mb-4">
              Used by the pay page for session-based payment flow. Job parameters are read from the
              session&apos;s stored payload, so only the session ID is needed.
            </p>
            <h4 className="text-xs text-o-muted uppercase tracking-wider mb-3">Request Body</h4>
            <ParamTable
              params={[
                { name: "session_id", type: "string", description: "Payment session ID from MCP flow", required: true },
                { name: "submitter_address", type: "string", description: "Your wallet address for tracking" },
              ]}
            />
            <h4 className="text-xs text-o-muted uppercase tracking-wider mt-4 mb-3">Headers</h4>
            <ParamTable
              params={[
                { name: "payment-signature", type: "string", description: "Signed x402 payment", required: true },
              ]}
            />
          </EndpointCard>

          <EndpointCard
            method="GET"
            path="/api/jobs/{job_id}"
            description="Get job details and output"
          >
            <p className="text-xs text-o-textSecondary">
              The job UUID serves as a capability token — anyone with the ID can view the job.
              Returns status, output, error_output, compute_duration_s, and price_usdc.
            </p>
          </EndpointCard>

          <EndpointCard
            method="GET"
            path="/api/stats"
            description="Aggregate P&L, job counts, sustainability ratio"
          />

          <EndpointCard
            method="GET"
            path="/api/wallet"
            description="Current ETH/USDC balances and recent snapshots"
          />

          <EndpointCard
            method="GET"
            path="/api/attribution"
            description="Builder code analytics and recent attribution entries"
          />

          <EndpointCard
            method="GET"
            path="/api/attribution/decode?tx_hash=0x..."
            description="Decode ERC-8021 builder codes from a transaction"
          />

          <EndpointCard
            method="GET"
            path="/api/capabilities"
            description="Machine-readable service manifest"
          >
            <p className="text-xs text-o-textSecondary">
              Returns payment protocol info, compute limits (max CPUs, max time), trust metrics
              (uptime), and rate limits. Useful for agent discovery.
            </p>
          </EndpointCard>

          <EndpointCard
            method="GET"
            path="/health"
            description="Liveness probe"
          />

          <EndpointCard
            method="GET"
            path="/health/ready"
            description="Readiness probe (checks DB, wallet)"
          />

          <EndpointCard
            method="POST"
            path="/api/sessions"
            description="Create a payment session (used by MCP server)"
          >
            <ParamTable
              params={[
                { name: "script", type: "string", description: "Shell script to execute (script mode, optional)" },
                { name: "job_payload", type: "object", description: "Job parameters for non-script modes (files, entrypoint, image, etc.)" },
                { name: "cpus", type: "int", description: "Number of CPU cores", required: true },
                { name: "time_limit_min", type: "int", description: "Max runtime in minutes", required: true },
                { name: "price", type: "string", description: "Price string from quote", required: true },
              ]}
            />
            <p className="text-xs text-o-textSecondary mt-3">
              Provide either <code className="text-o-blueText">script</code> for script mode
              or <code className="text-o-blueText">job_payload</code> for multi-file and other modes.
            </p>
          </EndpointCard>

          <EndpointCard
            method="GET"
            path="/api/sessions/{session_id}"
            description="Get payment session details (10-min TTL)"
          />

          <EndpointCard
            method="POST"
            path="/api/sessions/{session_id}/complete"
            description="Mark payment session as paid"
          >
            <ParamTable
              params={[
                { name: "job_id", type: "string", description: "Job ID from successful payment", required: true },
              ]}
            />
          </EndpointCard>
        </div>
      </section>
    </>
  );
}
