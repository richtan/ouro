import CodeBlock from "@/components/docs/CodeBlock";
import ParamTable from "@/components/docs/ParamTable";

const INSTALL = `pip install ouro-sdk`;

const QUICKSTART = `import asyncio
from ouro_sdk import OuroClient

async def main():
    async with OuroClient() as ouro:
        # Get a price quote
        quote = await ouro.quote(cpus=1, time_limit_min=1)
        print(f"Price: {quote.price}")

        # Submit and wait for results (requires x402-capable HTTP client)
        result = await ouro.run(script="echo hello world")
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
    result = await ouro.run(script="python3 train.py --epochs 50", cpus=2, time_limit_min=30)`;

const MULTIFILE_EXAMPLE = `from ouro_sdk import OuroClient

async with OuroClient(client=x402_client) as ouro:
    result = await ouro.run(
        files=[
            {"path": "train.py", "content": """
import torch
import torch.nn as nn
from model import SimpleNet

net = SimpleNet()
print(f"Parameters: {sum(p.numel() for p in net.parameters())}")
"""},
            {"path": "model.py", "content": """
import torch.nn as nn

class SimpleNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(784, 10)

    def forward(self, x):
        return self.fc(x)
"""},
        ],
        entrypoint="train.py",
        image="ouro-python",
        cpus=1,
        time_limit_min=5,
    )
    print(result.output)`;

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

      {/* Multi-file */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">Multi-File Jobs</h2>
        <p className="text-sm text-o-textSecondary mb-4">
          For projects with multiple files, pass a{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            files
          </span>{" "}
          list and an{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            entrypoint
          </span>{" "}
          instead of a script. Each file is a dict with{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            path
          </span>{" "}
          and{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            content
          </span>{" "}
          keys. Use the{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            image
          </span>{" "}
          parameter to select a container environment.
        </p>
        <CodeBlock filename="multi_file.py" language="python" copyText={MULTIFILE_EXAMPLE}>
          {MULTIFILE_EXAMPLE}
        </CodeBlock>
        <div className="mt-4">
          <p className="text-xs text-o-textSecondary">
            Available images:{" "}
            {["ouro-ubuntu", "ouro-python", "ouro-nodejs"].map((img) => (
              <span
                key={img}
                className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text mr-1.5"
              >
                {img}
              </span>
            ))}
          </p>
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
              <span className="font-mono">await ouro.run(*, script?, files?, entrypoint?, image, cpus, time_limit_min)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Submit a job and wait for completion. Provide{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">script</span>{" "}
              or{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">files</span>
              {" "}+{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">entrypoint</span>.
              Returns a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">JobResult</span>.
            </p>
            <ParamTable
              params={[
                { name: "script", type: "str | None", description: "Shell script string (mutually exclusive with files)" },
                { name: "files", type: "list[dict] | None", description: 'List of {path, content} dicts (mutually exclusive with script)' },
                { name: "entrypoint", type: "str | None", description: "File to execute when using files mode" },
                { name: "image", type: "str", description: 'Container image (default: "ouro-ubuntu")' },
                { name: "cpus", type: "int", description: "Number of CPU cores (default: 1, max: 8)" },
                { name: "time_limit_min", type: "int", description: "Time limit in minutes (default: 1)" },
                { name: "submitter_address", type: "str | None", description: "Wallet address of the submitter" },
                { name: "builder_code", type: "str | None", description: "ERC-8021 builder code for attribution" },
              ]}
            />
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-o-text mb-2">
              <span className="font-mono">await ouro.submit(*, script?, files?, entrypoint?, image, cpus, time_limit_min)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Submit a job without waiting. Same parameters as{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">run()</span>.
              Returns the{" "}
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
              <span className="font-mono">await ouro.quote(cpus=1, time_limit_min=1, submission_mode=&quot;script&quot;)</span>
            </h3>
            <p className="text-sm text-o-textSecondary mb-3">
              Get a price quote without submitting. Use{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">submission_mode</span>{" "}
              to specify the job type ({`"script"`}, {`"multi_file"`}, {`"archive"`}, or {`"git"`}).
              Returns a{" "}
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
