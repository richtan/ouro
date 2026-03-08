import CodeBlock from "@/components/docs/CodeBlock";
import ParamTable from "@/components/docs/ParamTable";
import StepCard from "@/components/docs/StepCard";

const TOOLS = [
  {
    name: "get_job_status",
    description:
      "Check the status of a job or payment session. Accepts either a job_id or session_id. Returns full details including output when completed.",
    params: [
      {
        name: "job_id",
        type: "string",
        description: "Job ID or session ID to check",
        required: true,
      },
    ],
    response: `{
  "id": "a1b2c3d4-...",
  "status": "completed",
  "output": "Hello world\\n",
  "compute_duration_s": 2.4,
  "price_usdc": 0.0841
}`,
  },
  {
    name: "get_price_quote",
    description: "Get a price quote without submitting or paying. Use this to check pricing before committing.",
    params: [
      { name: "cpus", type: "int", description: "Number of CPU cores (default 1, max 8)" },
      { name: "time_limit_min", type: "int", description: "Max runtime in minutes (default 1)" },
      { name: "submission_mode", type: "string", description: "Submission mode: script, multi_file, archive, git (default: script)" },
    ],
    response: `{
  "price": "$0.0841",
  "breakdown": {
    "gas_upper_bound": 0.0025,
    "llm_upper_bound": 0.01,
    "compute_cost": 0.0006,
    "setup_cost": 0.0,
    "cost_floor": 0.0131,
    "margin_multiplier": 1.5,
    "demand_multiplier": 1.0,
    "submission_mode": "script",
    "phase": "OPTIMAL"
  },
  "guaranteed_profitable": true
}`,
  },
  {
    name: "get_payment_requirements",
    description:
      "Get x402 payment requirements for a job. Returns the raw PAYMENT-REQUIRED header that your x402 library needs to construct and sign a USDC payment. Step 1 of the autonomous flow.",
    params: [
      { name: "script", type: "string", description: "Shell script to execute (use this OR files+entrypoint)" },
      { name: "files", type: "array", description: "Array of {path, content} file objects for multi-file jobs" },
      { name: "entrypoint", type: "string", description: "Entry script path relative to workspace (required with files)" },
      { name: "image", type: "string", description: "Container image: ouro-ubuntu, ouro-python, ouro-nodejs (default: ouro-ubuntu)" },
      { name: "cpus", type: "int", description: "Number of CPU cores (default 1, max 8)" },
      { name: "time_limit_min", type: "int", description: "Max runtime in minutes (default 1)" },
      { name: "submitter_address", type: "string", description: "Your wallet address (optional)" },
      { name: "builder_code", type: "string", description: "Builder code for attribution (optional)" },
    ],
    response: `{
  "price": "$0.0841",
  "breakdown": { ... },
  "submission_mode": "script",
  "setup_cost": 0.0,
  "payment_required_header": "eyJ0eXAiOiJ4NDAyL...",
  "message": "Payment of $0.0841 USDC required on Base..."
}`,
  },
  {
    name: "submit_and_pay",
    description:
      "Submit a job with a pre-signed x402 payment. Step 2 of the autonomous flow — call after signing the payment header from get_payment_requirements.",
    params: [
      { name: "script", type: "string", description: "Shell script to execute (use this OR files+entrypoint, must match step 1)" },
      { name: "files", type: "array", description: "Array of {path, content} file objects (must match step 1)" },
      { name: "entrypoint", type: "string", description: "Entry script path (must match step 1)" },
      { name: "image", type: "string", description: "Container image (must match step 1)" },
      { name: "payment_signature", type: "string", description: "Signed x402 payment string", required: true },
      { name: "cpus", type: "int", description: "Number of CPU cores (must match step 1)" },
      { name: "time_limit_min", type: "int", description: "Max runtime in minutes (must match)" },
      { name: "submitter_address", type: "string", description: "Your wallet address (optional)" },
      { name: "builder_code", type: "string", description: "Builder code (must match if used in step 1)" },
    ],
    response: `{
  "job_id": "a1b2c3d4-...",
  "status": "pending",
  "submission_mode": "script",
  "price": "$0.0841",
  "message": "Job a1b2c3d4-... submitted successfully."
}`,
  },
  {
    name: "get_allowed_images",
    description:
      "Returns the list of available container images for compute jobs. Each image is pre-built with common tools for its ecosystem.",
    params: [],
    response: `{
  "images": [
    { "id": "ouro-ubuntu", "description": "Ubuntu 22.04 base image" },
    { "id": "ouro-python", "description": "Python 3.12 with pip" },
    { "id": "ouro-nodejs", "description": "Node.js 20 LTS" }
  ],
  "default": "ouro-ubuntu"
}`,
  },
  {
    name: "get_api_endpoint",
    description: "Get the direct API endpoint URL, method, and body schema for programmatic access without MCP.",
    params: [],
    response: `{
  "url": "https://api.ourocompute.com/api/compute/submit",
  "method": "POST",
  "payment_protocol": "x402",
  "network": "eip155:8453",
  "currency": "USDC",
  "body_schema": {
    "script": "string (required)",
    "cpus": "int (default 1, max 8)",
    "time_limit_min": "int (default 1)",
    "submitter_address": "string (optional)"
  }
}`,
  },
];

export default function McpToolsPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          MCP Tools Reference
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Full schemas and example responses for all 6 tools.
        </p>
      </div>

      {/* Tool sections */}
      {TOOLS.map((tool, i) => (
        <section
          key={tool.name}
          className={i > 0 ? "border-t border-o-border mt-10 pt-10" : ""}
        >
          <h2 className="font-display text-lg font-bold text-o-text mb-1">
            <span className="font-mono">{tool.name}</span>
          </h2>
          <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
            {tool.description}
          </p>

          {tool.params.length > 0 && (
            <div className="mb-4">
              <h3 className="font-display text-sm font-semibold text-o-text mb-3">
                Parameters
              </h3>
              <ParamTable params={tool.params} />
            </div>
          )}

          <h3 className="font-display text-sm font-semibold text-o-text mb-3">
            Example Response
          </h3>
          <CodeBlock filename="response.json" language="json" copyText={tool.response}>
            {tool.response}
          </CodeBlock>
        </section>
      ))}

      {/* Payment flow */}
      <section className="border-t border-o-border mt-10 pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">
          Payment Flow
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-6">
          For agents with their own wallet. No human interaction needed.
        </p>
        <div>
          <StepCard number={1} title="Get payment requirements">
            <p>
              Call{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                get_payment_requirements
              </span>{" "}
              with your job details. Returns the x402 payment header.
            </p>
          </StepCard>
          <StepCard number={2} title="Sign payment locally">
            <p>
              Decode the{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                payment_required_header
              </span>{" "}
              with your x402 library and sign the USDC payment with your wallet.
              No private keys leave your agent.
            </p>
          </StepCard>
          <StepCard number={3} title="Submit with payment">
            <p>
              Call{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                submit_and_pay
              </span>{" "}
              with the script and signed payment signature. Complete within 30 seconds of step 1.
            </p>
          </StepCard>
          <StepCard number={4} title="Poll for results" last>
            <p>
              Call{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                get_job_status
              </span>{" "}
              with the returned{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                job_id
              </span>
              . Returns output when complete.
            </p>
          </StepCard>
        </div>
      </section>
    </>
  );
}
