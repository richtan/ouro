"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAccount, useWalletClient, usePublicClient } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { x402Client } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { wrapFetchWithPayment } from "@x402/fetch";

type JobStatus = "idle" | "submitting" | "paying" | "error";

const TEMPLATES = [
  {
    name: "Hello World",
    script: '#!/bin/bash\necho "Hello from Ouro HPC cluster!"\nhostname && uptime',
  },
  {
    name: "Python Math",
    script: '#!/bin/bash\npython3 -c "import math; print(f\'100! = {math.factorial(100)}\')"',
  },
  {
    name: "Benchmark",
    script: "#!/bin/bash\ndd if=/dev/zero of=/dev/null bs=1M count=100 2>&1\necho \"Benchmark complete\"",
  },
  {
    name: "System Info",
    script: "#!/bin/bash\necho '=== CPU ==='\nnproc\necho '=== Memory ==='\nfree -h 2>/dev/null || echo 'N/A'\necho '=== Disk ==='\ndf -h / 2>/dev/null\necho '=== Uptime ==='\nuptime",
  },
];

export default function SubmitPage() {
  const router = useRouter();
  const { address, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();
  const publicClient = usePublicClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [script, setScript] = useState(TEMPLATES[0].script);
  const [nodes, setNodes] = useState(1);
  const [timeLimit, setTimeLimit] = useState(1);
  const [builderCode, setBuilderCode] = useState("");
  const [status, setStatus] = useState<JobStatus>("idle");
  const [error, setError] = useState("");

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text === "string") setScript(text);
    };
    reader.readAsText(file);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text === "string") setScript(text);
    };
    reader.readAsText(file);
  }, []);

  const handleSubmit = async () => {
    if (!walletClient || !publicClient || !isConnected) return;
    setStatus("submitting");
    setError("");

    try {
      const signer = toClientEvmSigner(
        {
          address: walletClient.account.address,
          signTypedData: (args: Record<string, unknown>) =>
            walletClient.signTypedData(args as Parameters<typeof walletClient.signTypedData>[0]),
        },
        publicClient,
      );
      const client = new x402Client();
      client.register("eip155:*", new ExactEvmScheme(signer));

      const fetchWithPay = wrapFetchWithPayment(fetch, client);

      setStatus("paying");

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (builderCode.trim()) {
        headers["X-BUILDER-CODE"] = builderCode.trim();
      }

      const res = await fetchWithPay("/api/proxy/submit", {
        method: "POST",
        headers,
        body: JSON.stringify({
          script,
          nodes,
          time_limit_min: timeLimit,
          submitter_address: address,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      router.push(`/history?expand=${data.job_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submission failed");
      setStatus("error");
    }
  };

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Submit Compute Job
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Write or upload a script, configure parameters, and pay with USDC via x402
        </p>
      </div>

      {!isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">Connect your wallet to submit compute jobs</p>
          <ConnectButton />
        </div>
      ) : (
        <div className="space-y-6">
          {/* File upload — prominent on all sizes */}
          <div className="card">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-3">
              <label className="stat-label">Script</label>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-3 py-2 text-xs font-medium text-o-blueText bg-o-blue/10 border border-o-blue/20 rounded-lg hover:bg-o-blue/20 transition-colors"
                >
                  Upload File
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".sh,.py,.bash,.txt,.r,.jl"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                {TEMPLATES.map((t) => (
                  <button
                    key={t.name}
                    onClick={() => setScript(t.script)}
                    className="px-2 py-1.5 text-xs text-o-textSecondary hover:text-o-blueText bg-o-bg border border-o-border rounded-lg transition-colors hover:border-o-blueText/30"
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <textarea
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={12}
                spellCheck={false}
                className="w-full bg-o-bg border border-o-border rounded-lg p-4 font-mono text-sm text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText resize-y leading-relaxed"
                placeholder="#!/bin/bash&#10;echo 'Your script here'"
              />
            </div>
            <p className="text-xs text-o-muted mt-2">
              Drag and drop a script file, or click Upload. Supports .sh, .py, .bash, .txt
            </p>
          </div>

          {/* Parameters */}
          <div className="card">
            <label className="stat-label mb-4 block">Parameters</label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-o-textSecondary">Nodes</span>
                  <span className="font-mono text-sm text-o-blueText">{nodes}</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={16}
                  value={nodes}
                  onChange={(e) => setNodes(Number(e.target.value))}
                  className="w-full accent-o-blue"
                />
                <div className="flex justify-between text-xs text-o-muted mt-1">
                  <span>1</span>
                  <span>16</span>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-o-textSecondary">Time Limit</span>
                  <span className="font-mono text-sm text-o-blueText">{timeLimit}m</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={60}
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(Number(e.target.value))}
                  className="w-full accent-o-blue"
                />
                <div className="flex justify-between text-xs text-o-muted mt-1">
                  <span>1 min</span>
                  <span>60 min</span>
                </div>
              </div>
              <div>
                <div className="mb-2">
                  <span className="text-xs text-o-textSecondary">Builder Code (optional)</span>
                </div>
                <input
                  type="text"
                  value={builderCode}
                  onChange={(e) => setBuilderCode(e.target.value)}
                  placeholder="your-builder-code"
                  className="w-full bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText"
                />
                <p className="text-xs text-o-muted mt-1">
                  ERC-8021 builder code for dual attribution
                </p>
              </div>
            </div>
          </div>

          {/* Submit */}
          <div className="card">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <p className="text-sm text-o-textSecondary">
                  Payment via <span className="text-o-blueText">x402</span> protocol
                  &mdash; you&apos;ll sign a USDC authorization when submitting
                </p>
                <p className="text-xs text-o-muted mt-1">
                  Connected: {address?.slice(0, 6)}...{address?.slice(-4)}
                </p>
              </div>
              <button
                onClick={handleSubmit}
                disabled={status === "submitting" || status === "paying" || !script.trim()}
                className="w-full sm:w-auto px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {status === "submitting" ? "Preparing..." : status === "paying" ? "Sign Payment..." : "Submit & Pay"}
              </button>
            </div>
          </div>

          {status === "error" && (
            <div className="card border-o-red/30">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2.5 h-2.5 rounded-full bg-o-red" />
                <span className="stat-label !text-o-red">Submission Failed</span>
              </div>
              <p className="text-xs text-o-red/80">{error}</p>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
