import CodeBlock from "@/components/docs/CodeBlock";
import ParamTable from "@/components/docs/ParamTable";

const INSTALL = `pip install ouro-sdk`;

const QUICKSTART = `import asyncio
from ouro_sdk import OuroClient

async def main():
    async with OuroClient() as ouro:
        # Get a price quote
        quote = await ouro.quote(nodes=1, time_limit_min=1)
        print(f"Price: {quote.price}")

        # Submit and wait for results (requires x402-capable HTTP client)
        result = await ouro.run("echo hello world")
        print(f"Output: {result.output}")
        print(f"Proof: {result.proof_tx_hash}")

asyncio.run(main())`;

const X402_EXAMPLE = `import httpx
from ouro_sdk import OuroClient

# Wrap your httpx client with x402 payment handling
# (see x402-python docs for setup)
x402_client = httpx.AsyncClient(...)  # your x402-wrapped client

async with OuroClient(client=x402_client) as ouro:
    # Payment is handled transparently by the x402 client
    result = await ouro.run("python3 train.py --epochs 50", nodes=2, time_limit_min=30)`;

export default function SdkPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Python SDK
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          OuroClient for programmatic access to the compute API.
        </p>
      </div>

      {/* Install */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">Install</h2>
        <CodeBlock filename="terminal" language="bash" copyText={INSTALL}>
          {INSTALL}
        </CodeBlock>
      </section>

      {/* Quick start */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">Quick Start</h2>
        <CodeBlock filename="main.py" language="python" copyText={QUICKSTART}>
          {QUICKSTART}
        </CodeBlock>
        <p className="text-sm text-o-textSecondary mt-4">
          The SDK does not handle x402 payment itself. Pass an x402-wrapped{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            httpx.AsyncClient
          </span>{" "}
          for automatic payment:
        </p>
        <div className="mt-4">
          <CodeBlock filename="with_x402.py" language="python" copyText={X402_EXAMPLE}>
            {X402_EXAMPLE}
          </CodeBlock>
        </div>
      </section>

      {/* Constructor */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          OuroClient
        </h2>
        <ParamTable
          params={[
            { name: "api_url", type: "str", description: 'API base URL (default: "https://api.ourocompute.com")' },
            { name: "client", type: "httpx.AsyncClient | None", description: "Custom HTTP client (for x402 wrapping)" },
            { name: "poll_interval_s", type: "float", description: "Poll interval in seconds (default 3.0)" },
            { name: "poll_timeout_s", type: "float", description: "Max poll duration in seconds (default 600.0)" },
          ]}
        />
      </section>

      {/* Methods */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">Methods</h2>

        <div className="space-y-8">
          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.run(script, nodes=1, time_limit_min=1)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Submit a job and wait for completion. Returns a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">JobResult</span>.
            </p>
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.submit(script, nodes=1, time_limit_min=1)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Submit a job without waiting. Returns the{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">job_id</span> string.
            </p>
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.wait(job_id)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Poll until job completes or fails. Uses exponential backoff. Returns a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">JobResult</span>.
            </p>
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.get_job(job_id)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Fetch current job status. Returns a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">JobResult</span>.
            </p>
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.quote(nodes=1, time_limit_min=1)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Get a price quote without submitting. Returns a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">Quote</span>.
            </p>
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.capabilities()</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Fetch the server capability manifest. Returns a dict.
            </p>
          </div>
        </div>
      </section>

      {/* Models */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">Models</h2>

        <div className="space-y-6">
          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-3">Quote</h3>
            <ParamTable
              params={[
                { name: "price", type: "str", description: 'Price string (e.g. "$0.0841")' },
                { name: "breakdown", type: "dict", description: "Cost breakdown details" },
                { name: "guaranteed_profitable", type: "bool", description: "Whether the price exceeds the cost floor" },
              ]}
            />
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-3">JobResult</h3>
            <ParamTable
              params={[
                { name: "job_id", type: "str", description: "Job UUID" },
                { name: "status", type: "str", description: 'Job status: "pending", "processing", "running", "completed", "failed"' },
                { name: "output", type: "str", description: "stdout from the job" },
                { name: "error_output", type: "str", description: "stderr from the job" },
                { name: "output_hash", type: "str | None", description: "SHA-256 hash of the output" },
                { name: "proof_tx_hash", type: "str | None", description: "On-chain proof transaction hash" },
                { name: "compute_duration_s", type: "float | None", description: "Actual compute time in seconds" },
                { name: "price_usdc", type: "float | None", description: "Price charged in USDC" },
              ]}
            />
          </div>
        </div>
      </section>
    </>
  );
}
