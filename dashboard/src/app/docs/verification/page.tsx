import CodeBlock from "@/components/docs/CodeBlock";
import StepCard from "@/components/docs/StepCard";

const DECODE_CURL = `curl "https://api.ourocompute.com/api/attribution/decode?tx_hash=0x..."`;

const DECODE_RESPONSE = `{
  "tx_hash": "0x...",
  "has_builder_codes": true,
  "builder_codes": ["ouro"],
  "schema_id": 0,
  "raw_suffix": "0x6f75726f..."
}`;

export default function VerificationPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Verification
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          On-chain proofs, output hashing, and ERC-8021 builder code attribution.
        </p>
      </div>

      {/* How proofs work */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">
          How Proofs Work
        </h2>
        <div>
          <StepCard number={1} title="Job completes on Slurm">
            <p>
              The Slurm cluster runs your script in an Apptainer container. On completion,
              stdout and stderr are captured.
            </p>
          </StepCard>
          <StepCard number={2} title="Output is hashed">
            <p>
              The agent computes{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                SHA-256(output)
              </span>{" "}
              to create a unique fingerprint of the job result.
            </p>
          </StepCard>
          <StepCard number={3} title="Proof posted on-chain">
            <p>
              The agent calls{" "}
              <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
                ProofOfCompute.submitProof(jobId, outputHash)
              </span>{" "}
              on Base. The transaction hash is stored with the job record.
            </p>
          </StepCard>
          <StepCard number={4} title="Verify anytime" last>
            <p>
              Anyone can verify a job&apos;s output by hashing the output and comparing it
              to the on-chain proof. The proof is immutable and publicly auditable on BaseScan.
            </p>
          </StepCard>
        </div>
      </section>

      {/* Contract */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Smart Contract
        </h2>
        <div className="bg-o-surface border border-o-border rounded-xl px-4 py-3.5">
          <span className="text-xs text-o-muted uppercase tracking-wider">ProofOfCompute</span>
          <p className="font-mono text-xs text-o-blueText mt-1 break-all">
            Deployed on Base (Chain ID: 8453)
          </p>
        </div>
        <p className="text-sm text-o-textSecondary mt-4 leading-relaxed">
          The contract stores{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            (jobId, outputHash, submitter, timestamp)
          </span>{" "}
          tuples. It prevents duplicate submissions and tracks per-submitter reputation
          (total proofs submitted).
        </p>
      </section>

      {/* Verifying on BaseScan */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Verifying a Proof
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          Every completed job includes a{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            proof_tx_hash
          </span>
          . To verify:
        </p>
        <ol className="text-sm text-o-textSecondary space-y-2 ml-4 list-decimal mb-4">
          <li>Get the job output from the API or your local copy</li>
          <li>
            Compute{" "}
            <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
              SHA-256(output)
            </span>
          </li>
          <li>
            Look up the{" "}
            <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
              proof_tx_hash
            </span>{" "}
            on BaseScan
          </li>
          <li>Compare the on-chain hash with your computed hash</li>
        </ol>
        <CodeBlock filename="terminal" copyText='echo -n "Hello world\n" | sha256sum'>
          <span className="text-o-muted">$ </span>
          <span className="text-o-text">echo -n &quot;Hello world\n&quot; | sha256sum</span>
          {"\n"}
          <span className="text-o-textSecondary">a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e</span>
        </CodeBlock>
      </section>

      {/* ERC-8021 */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          ERC-8021 Builder Codes
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          Every on-chain transaction from Ouro includes an ERC-8021 builder code suffix
          in the calldata. This provides attribution for which builder triggered the
          transaction.
        </p>

        <div className="bg-o-surface border border-o-border rounded-xl p-4 mb-6">
          <h3 className="font-display text-sm font-semibold text-o-text mb-3">Suffix Format</h3>
          <div className="font-mono text-xs text-o-textSecondary leading-relaxed">
            <span className="text-o-text">calldata</span> +{" "}
            <span className="text-o-blueText">builderCodes</span> +{" "}
            <span className="text-o-amber">length (1 byte)</span> +{" "}
            <span className="text-o-green">schemaId (0x00)</span> +{" "}
            <span className="text-o-muted">marker (16 bytes)</span>
          </div>
        </div>

        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          You can include your own builder code when submitting jobs via the{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            X-BUILDER-CODE
          </span>{" "}
          header or{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            builder_code
          </span>{" "}
          MCP parameter.
        </p>

        <h3 className="font-display text-sm font-semibold text-o-text mb-3 mt-6">
          Decode a Transaction
        </h3>
        <CodeBlock filename="terminal" language="bash" copyText={DECODE_CURL}>
          {DECODE_CURL}
        </CodeBlock>
        <div className="mt-4">
          <CodeBlock filename="response.json" language="json" copyText={DECODE_RESPONSE}>
            {DECODE_RESPONSE}
          </CodeBlock>
        </div>
      </section>
    </>
  );
}
