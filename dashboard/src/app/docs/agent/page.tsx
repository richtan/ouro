import CodeBlock from "@/components/docs/CodeBlock";
import StepCard from "@/components/docs/StepCard";

const PACKAGE_JSON = `{
  "dependencies": {
    "x402-next": "^0.1.0",
    "viem": "^2.0.0"
  }
}`;

const AGENT_TS = `import { createWalletClient, http, parseUnits } from "viem";
import { base } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";
import { wrapEIP5792Actions } from "viem/experimental";

// 1. Set up your wallet
const account = privateKeyToAccount(process.env.PRIVATE_KEY as \`0x\${string}\`);
const wallet = createWalletClient({
  account,
  chain: base,
  transport: http(),
});

const OURO_API = "https://api.ourocompute.com";

async function runJob(script: string, cpus = 1, timeMin = 1) {
  // 2. Get price and payment requirements
  const quoteRes = await fetch(\`\${OURO_API}/api/compute/submit\`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script, cpus, time_limit_min: timeMin }),
  });

  if (quoteRes.status !== 402) throw new Error("Expected 402");

  const paymentHeader = quoteRes.headers.get("payment-required");
  const { price } = await quoteRes.json();
  console.log(\`Price: \${price} USDC\`);

  // 3. Sign x402 payment with your wallet
  // (Use your x402 library to decode the header and sign)
  const paymentSignature = await signX402Payment(paymentHeader, wallet);

  // 4. Submit with signed payment
  const submitRes = await fetch(\`\${OURO_API}/api/compute/submit\`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "payment-signature": paymentSignature,
    },
    body: JSON.stringify({ script, cpus, time_limit_min: timeMin }),
  });

  const { job_id } = await submitRes.json();
  console.log(\`Job submitted: \${job_id}\`);

  // 5. Poll for results
  let result;
  while (true) {
    const res = await fetch(\`\${OURO_API}/api/jobs/\${job_id}\`);
    result = await res.json();
    if (result.status === "completed" || result.status === "failed") break;
    await new Promise((r) => setTimeout(r, 3000));
  }

  console.log(\`Status: \${result.status}\`);
  console.log(\`Output: \${result.output}\`);
  console.log(\`Proof: \${result.proof_tx_hash}\`);
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
          Build an agent that pays for and runs HPC jobs with its own wallet.
        </p>
      </div>

      {/* Overview */}
      <section className="mb-10">
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          Autonomous agents interact with Ouro via the x402 payment protocol. The agent signs
          USDC payments locally — no private keys leave your agent, only the opaque payment
          signature is transmitted.
        </p>
        <div className="bg-o-surface border border-o-border rounded-xl p-4">
          <h3 className="font-display text-sm font-semibold text-o-text mb-3">Prerequisites</h3>
          <ul className="text-sm text-o-textSecondary space-y-1 ml-4 list-disc">
            <li>Node.js 18+ or Python 3.10+</li>
            <li>A wallet with USDC on Base</li>
            <li>An x402-compatible signing library</li>
          </ul>
        </div>
      </section>

      {/* Flow */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">
          Payment Flow
        </h2>
        <div>
          <StepCard number={1} title="POST without payment → get price">
            <p>
              Send your job to{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                POST /api/compute/submit
              </span>{" "}
              without a payment header. You&apos;ll receive a 402 response with the price and
              a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                PAYMENT-REQUIRED
              </span>{" "}
              header.
            </p>
          </StepCard>
          <StepCard number={2} title="Decode and sign locally">
            <p>
              Use your x402 library to decode the payment header and sign a USDC
              authorization with your wallet. The signature is valid for ~30 seconds.
            </p>
          </StepCard>
          <StepCard number={3} title="POST with payment → job created">
            <p>
              Re-send the same request with the{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                payment-signature
              </span>{" "}
              header. You&apos;ll get back a{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                job_id
              </span>
              .
            </p>
          </StepCard>
          <StepCard number={4} title="Poll for results" last>
            <p>
              GET{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                /api/jobs/{"{job_id}"}
              </span>{" "}
              every 3 seconds. When{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                status
              </span>{" "}
              is{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                completed
              </span>
              , the output and on-chain proof hash are included.
            </p>
          </StepCard>
        </div>
      </section>

      {/* Data flow diagram */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Data Flow
        </h2>
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
          <span className="text-o-textSecondary">{"Workers"}</span>{"\n"}
          <span className="text-o-blueText">{"Ouro API"}</span>
          <span className="text-o-muted">{" ──proof──▶ "}</span>
          <span className="text-o-textSecondary">{"Base (on-chain)"}</span>
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
    </>
  );
}
