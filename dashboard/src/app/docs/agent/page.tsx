import Link from "next/link";
import CodeBlock from "@/components/docs/CodeBlock";

const PACKAGE_JSON = `{
  "dependencies": {
    "@x402/fetch": "^2.6.0",
    "@x402/evm": "^2.6.0",
    "viem": "^2.0.0"
  }
}`;

const AGENT_TS = `import { wrapFetchWithPaymentFromConfig } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm";
import { privateKeyToAccount } from "viem/accounts";

// 1. Set up wallet and x402-enabled fetch
const account = privateKeyToAccount(process.env.PRIVATE_KEY as \`0x\${string}\`);
const fetchWithPayment = wrapFetchWithPaymentFromConfig(fetch, {
  schemes: [{ network: "eip155:8453", client: new ExactEvmScheme(account) }],
});
// fetchWithPayment handles 402 → sign → retry automatically

const OURO_API = "https://api.ourocompute.com";

async function runJob(script: string, cpus = 1, timeMin = 1) {
  // 2. Submit job — payment is handled automatically
  const submitRes = await fetchWithPayment(\`\${OURO_API}/api/compute/submit\`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script, cpus, time_limit_min: timeMin }),
  });

  const { job_id } = await submitRes.json();
  console.log(\`Job submitted: \${job_id}\`);

  // 3. Poll for results
  // GET /api/jobs/{job_id} requires EIP-191 wallet signature.
  // Sign message "ouro-job-view:{job_id}:{wallet}:{timestamp}" and pass
  // wallet, signature, timestamp as query params. See API docs for details.
  let result;
  while (true) {
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const message = \`ouro-job-view:\${job_id}:\${account.address.toLowerCase()}:\${timestamp}\`;
    const signature = await account.signMessage({ message });
    const params = new URLSearchParams({
      wallet: account.address, signature, timestamp,
    });
    const res = await fetch(\`\${OURO_API}/api/jobs/\${job_id}?\${params}\`);
    result = await res.json();
    if (["completed", "failed"].includes(result.status)) break;
    await new Promise((r) => setTimeout(r, 3000));
  }

  console.log(\`Status: \${result.status}\`);
  console.log(\`Output: \${result.output}\`);
  return result;
}

runJob("echo hello from autonomous agent");`;

export default function AgentPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Building an Autonomous Agent
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Build an agent that pays for and runs compute jobs with its own wallet.
        </p>
      </div>

      {/* Overview */}
      <section className="mb-10">
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          Use{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">@x402/fetch</span>{" "}
          to wrap the standard <span className="font-mono text-xs text-o-text">fetch</span> function
          with automatic x402 payment handling. When your request gets a 402 response, the library
          signs the USDC payment with your wallet and retries — no manual payment code needed.
        </p>
        <div className="bg-o-surface border border-o-border rounded-xl p-4">
          <h3 className="font-display text-sm font-semibold text-o-text mb-3">Prerequisites</h3>
          <ul className="text-sm text-o-textSecondary space-y-1 ml-4 list-disc">
            <li>Node.js 18+</li>
            <li>A wallet with USDC on Base</li>
            <li>
              <span className="font-mono text-xs text-o-text">@x402/fetch</span> and{" "}
              <span className="font-mono text-xs text-o-text">@x402/evm</span> packages
            </li>
          </ul>
        </div>
      </section>

      {/* Payment flow link */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Payment Flow
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed">
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">@x402/fetch</span>{" "}
          handles the full payment flow automatically. For the step-by-step details of what
          happens under the hood, see the{" "}
          <Link href="/docs/api#payment-flow" className="text-o-blueText hover:underline">
            API payment flow
          </Link>.
        </p>
      </section>

      {/* Data flow diagram */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          What Happens Under the Hood
        </h2>
        <p className="text-xs text-o-muted mb-3">
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">@x402/fetch</span>{" "}
          handles this entire flow automatically — you just call <span className="font-mono text-xs text-o-text">fetchWithPayment()</span>.
        </p>
        <CodeBlock filename="architecture">
          <span className="text-o-textSecondary">{"Your Agent"}</span>
          <span className="text-o-muted">{" ──POST (no payment)──▶ "}</span>
          <span className="text-o-blueText">{"Ouro API"}</span>
          <span className="text-o-muted">{" ──▶ "}</span>
          <span className="text-o-amber">{"402 + price"}</span>{"\n"}
          <span className="text-o-textSecondary">{"Your Agent"}</span>
          <span className="text-o-muted">{" ──sign payment────▶ "}</span>
          <span className="text-o-textSecondary">{"Your Wallet"}</span>
          <span className="text-o-muted">{" (local)"}</span>{"\n"}
          <span className="text-o-textSecondary">{"Your Agent"}</span>
          <span className="text-o-muted">{" ──POST + signature──▶ "}</span>
          <span className="text-o-blueText">{"Ouro API"}</span>
          <span className="text-o-muted">{" ──▶ "}</span>
          <span className="text-o-green">{"200 + job_id"}</span>{"\n"}
          <span className="text-o-blueText">{"Ouro API"}</span>
          <span className="text-o-muted">{" ──submit──▶ "}</span>
          <span className="text-o-textSecondary">{"Slurm Cluster"}</span>
          <span className="text-o-muted">{" ──run──▶ "}</span>
          <span className="text-o-textSecondary">{"Workers"}</span>
        </CodeBlock>
      </section>

      {/* Dependencies */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Dependencies
        </h2>
        <CodeBlock filename="package.json" language="json" copyText={PACKAGE_JSON}>
          {PACKAGE_JSON}
        </CodeBlock>
      </section>

      {/* Full example */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Full Example
        </h2>
        <p className="text-sm text-o-textSecondary mb-4">
          A complete TypeScript agent that submits a job and polls for results:
        </p>
        <CodeBlock filename="agent.ts" language="typescript" copyText={AGENT_TS}>
          {AGENT_TS}
        </CodeBlock>
      </section>

      {/* Next page */}
      <div className="border-t border-o-border mt-12 pt-6 flex justify-end">
        <Link
          href="/docs/pricing"
          className="text-sm text-o-blueText hover:underline flex items-center gap-1"
        >
          Pricing <span aria-hidden="true">→</span>
        </Link>
      </div>
    </>
  );
}
