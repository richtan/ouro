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

      await res.json();
      router.push("/history");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submission failed");
      setStatus("error");
    }
  };

  return (
    <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
          Submit Compute Job
        </h1>
        <p className="font-body text-sm text-ouro-muted mt-1">
          Write or upload a script, configure parameters, and pay with USDC via x402
        </p>
      </div>

      {!isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-ouro-muted text-sm">Connect your wallet to submit compute jobs</p>
          <ConnectButton />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Script Editor */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <label className="stat-label">Script</label>
              <div className="flex items-center gap-2">
                {TEMPLATES.map((t) => (
                  <button
                    key={t.name}
                    onClick={() => setScript(t.script)}
                    className="px-2 py-1 text-[10px] font-mono text-ouro-muted hover:text-ouro-accent bg-black/30 border border-ouro-border/30 rounded transition-colors hover:border-ouro-accent/30"
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              className="relative"
            >
              <textarea
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={12}
                spellCheck={false}
                className="w-full bg-black/40 border border-ouro-border/40 rounded-lg p-4 font-mono text-sm text-ouro-text placeholder-ouro-muted/40 focus:outline-none focus:border-ouro-accent/50 resize-y leading-relaxed"
                placeholder="#!/bin/bash&#10;echo 'Your script here'"
              />
              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-3 py-1.5 text-[10px] font-mono text-ouro-muted bg-black/60 border border-ouro-border/30 rounded hover:border-ouro-accent/30 hover:text-ouro-accent transition-colors"
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
              </div>
            </div>
            <p className="text-[10px] text-ouro-muted mt-2">
              Drag and drop a script file, or click Upload. Supports .sh, .py, .bash, .txt
            </p>
          </div>

          {/* Parameters */}
          <div className="card">
            <label className="stat-label mb-4 block">Parameters</label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-ouro-muted">Nodes</span>
                  <span className="font-mono text-sm text-ouro-accent">{nodes}</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={16}
                  value={nodes}
                  onChange={(e) => setNodes(Number(e.target.value))}
                  className="w-full accent-ouro-accent"
                />
                <div className="flex justify-between text-[10px] text-ouro-muted mt-1">
                  <span>1</span>
                  <span>16</span>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-ouro-muted">Time Limit</span>
                  <span className="font-mono text-sm text-ouro-accent">{timeLimit}m</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={60}
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(Number(e.target.value))}
                  className="w-full accent-ouro-accent"
                />
                <div className="flex justify-between text-[10px] text-ouro-muted mt-1">
                  <span>1 min</span>
                  <span>60 min</span>
                </div>
              </div>
              <div>
                <div className="mb-2">
                  <span className="text-xs text-ouro-muted">Builder Code (optional)</span>
                </div>
                <input
                  type="text"
                  value={builderCode}
                  onChange={(e) => setBuilderCode(e.target.value)}
                  placeholder="your-builder-code"
                  className="w-full bg-black/40 border border-ouro-border/40 rounded px-3 py-2 font-mono text-xs text-ouro-text placeholder-ouro-muted/40 focus:outline-none focus:border-ouro-accent/50"
                />
                <p className="text-[10px] text-ouro-muted mt-1">
                  ERC-8021 builder code for dual attribution
                </p>
              </div>
            </div>
          </div>

          {/* Submit */}
          <div className="card">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-ouro-muted">
                  Payment via <span className="text-ouro-accent">x402</span> protocol
                  &mdash; you&apos;ll sign a USDC authorization when submitting
                </p>
                <p className="text-xs text-ouro-muted/60 mt-1">
                  Connected: {address?.slice(0, 6)}...{address?.slice(-4)}
                </p>
              </div>
              <button
                onClick={handleSubmit}
                disabled={status === "submitting" || status === "paying" || !script.trim()}
                className="px-6 py-3 bg-ouro-accent text-ouro-bg font-display font-bold text-sm rounded-lg hover:bg-ouro-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {status === "submitting" ? "Preparing..." : status === "paying" ? "Sign Payment..." : "Submit & Pay"}
              </button>
            </div>
          </div>

          {status === "error" && (
            <div className="card border-ouro-red/30">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2.5 h-2.5 rounded-full bg-ouro-red" />
                <span className="stat-label text-ouro-red">Submission Failed</span>
              </div>
              <p className="font-mono text-xs text-ouro-red/80">{error}</p>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
