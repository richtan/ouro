"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAccount, useWalletClient, usePublicClient } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { x402Client } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { wrapFetchWithPayment } from "@x402/fetch";

type JobStatus = "idle" | "submitting" | "paying" | "error";
type SubmissionMode = "script" | "files";

interface WorkspaceFile {
  path: string;
  content: string;
}

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

const IMAGES = [
  { id: "base", label: "Ubuntu 22.04" },
  { id: "python312", label: "Python 3.12" },
  { id: "node20", label: "Node.js 20" },
  { id: "pytorch", label: "PyTorch" },
  { id: "r-base", label: "R 4.4" },
];

export default function SubmitPage() {
  const router = useRouter();
  const { address, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();
  const publicClient = usePublicClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<SubmissionMode>("script");
  const [script, setScript] = useState(TEMPLATES[0].script);
  const [files, setFiles] = useState<WorkspaceFile[]>([{ path: "main.py", content: 'print("Hello from Ouro!")' }]);
  const [entrypoint, setEntrypoint] = useState("main.py");
  const [image, setImage] = useState("base");
  const [nodes, setNodes] = useState(1);
  const [timeLimit, setTimeLimit] = useState(1);
  const [builderCode, setBuilderCode] = useState("");
  const [status, setStatus] = useState<JobStatus>("idle");
  const [error, setError] = useState("");
  const [priceEstimate, setPriceEstimate] = useState<string | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);

  // B4: Live price estimate — debounced fetch
  useEffect(() => {
    setPriceLoading(true);
    const timeout = setTimeout(() => {
      const submissionMode = mode === "files" ? "multi_file" : "script";
      fetch(`/api/proxy/price?nodes=${nodes}&time_limit_min=${timeLimit}&submission_mode=${submissionMode}`)
        .then((r) => r.json())
        .then((data) => {
          setPriceEstimate(data.price ?? null);
          setPriceLoading(false);
        })
        .catch(() => {
          setPriceEstimate(null);
          setPriceLoading(false);
        });
    }, 300);
    return () => clearTimeout(timeout);
  }, [nodes, timeLimit, mode]);

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

  const addFile = () => {
    setFiles([...files, { path: "", content: "" }]);
  };

  const removeFile = (index: number) => {
    const removedPath = files[index]?.path;
    const updated = files.filter((_, i) => i !== index);
    setFiles(updated);
    if (entrypoint === removedPath && updated.length > 0) {
      setEntrypoint(updated[0].path);
    }
  };

  const updateFile = (index: number, field: "path" | "content", value: string) => {
    const updated = [...files];
    const oldPath = updated[index].path;
    updated[index] = { ...updated[index], [field]: value };
    setFiles(updated);
    // B3: Auto-sync entrypoint when path changes
    if (field === "path" && entrypoint === oldPath) {
      setEntrypoint(value);
    }
  };

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

      let body: Record<string, unknown>;
      if (mode === "script") {
        body = {
          script,
          nodes,
          time_limit_min: timeLimit,
          submitter_address: address,
          ...(image !== "base" && { image }),
        };
      } else {
        body = {
          files: files.map((f) => ({ path: f.path, content: f.content })),
          entrypoint,
          image,
          nodes,
          time_limit_min: timeLimit,
          submitter_address: address,
        };
      }

      const res = await fetchWithPay("/api/proxy/submit", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const respBody = await res.json().catch(() => ({}));
        throw new Error(respBody.detail || respBody.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      router.push(`/history?expand=${data.job_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submission failed");
      setStatus("error");
    }
  };

  const canSubmit =
    status !== "submitting" &&
    status !== "paying" &&
    (mode === "script"
      ? script.trim().length > 0
      : files.length > 0 && files.every((f) => f.path.trim() && f.content.trim()) && entrypoint.trim());

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Submit Compute Job
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Write a script or set up a multi-file workspace, configure parameters, and pay with USDC via x402
        </p>
      </div>

      {!isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">Connect your wallet to submit compute jobs</p>
          <ConnectButton />
        </div>
      ) : (
        <div className="space-y-6">
          {/* B1: Mode Tabs with descriptions */}
          <div className="flex gap-1 border-b border-o-border">
            <button
              onClick={() => setMode("script")}
              className={`px-4 py-2.5 transition-colors border-b-2 -mb-px ${
                mode === "script"
                  ? "text-o-blueText border-o-blue"
                  : "text-o-textSecondary border-transparent hover:text-o-text"
              }`}
            >
              <span className="text-sm font-medium block">Script</span>
              <span className="text-xs text-o-muted block mt-0.5">Run a single shell script</span>
            </button>
            <button
              onClick={() => setMode("files")}
              className={`px-4 py-2.5 transition-colors border-b-2 -mb-px ${
                mode === "files"
                  ? "text-o-blueText border-o-blue"
                  : "text-o-textSecondary border-transparent hover:text-o-text"
              }`}
            >
              <span className="text-sm font-medium block">Multi-File Workspace</span>
              <span className="text-xs text-o-muted block mt-0.5">Upload multiple source files</span>
            </button>
          </div>

          {/* Script Tab */}
          {mode === "script" && (
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
          )}

          {/* Multi-File Tab */}
          {mode === "files" && (
            <div className="space-y-4">
              {/* B3: Entrypoint selector at top */}
              <div className="card">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex-1">
                    <label className="text-xs text-o-textSecondary uppercase tracking-wider block mb-2">File to execute</label>
                    <select
                      value={entrypoint}
                      onChange={(e) => setEntrypoint(e.target.value)}
                      className="w-full bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text focus:outline-none focus:border-o-blueText"
                    >
                      {files
                        .filter((f) => f.path.trim())
                        .map((f) => (
                          <option key={f.path} value={f.path}>
                            {f.path}
                          </option>
                        ))}
                    </select>
                  </div>
                </div>
                <p className="text-xs text-o-muted mt-2">
                  The selected file will be run using the detected interpreter (.py → python3, .r → Rscript, etc.)
                </p>
              </div>

              {/* File cards */}
              {files.map((file, i) => (
                <div key={i} className="card">
                  <div className="flex items-center justify-between mb-3">
                    <input
                      type="text"
                      value={file.path}
                      onChange={(e) => updateFile(i, "path", e.target.value)}
                      placeholder="path/to/file.py"
                      className="bg-transparent font-mono text-sm text-o-blueText placeholder-o-muted focus:outline-none w-48 sm:w-64"
                    />
                    {files.length > 1 && (
                      <button
                        onClick={() => removeFile(i)}
                        className="px-2 py-1.5 text-xs text-o-red hover:text-o-red/80 transition-colors"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                  <textarea
                    value={file.content}
                    onChange={(e) => updateFile(i, "content", e.target.value)}
                    rows={6}
                    spellCheck={false}
                    className="w-full bg-o-bg border border-o-border rounded-lg p-4 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText resize-y leading-relaxed"
                    placeholder="File content..."
                  />
                </div>
              ))}
              <button
                onClick={addFile}
                className="w-full py-3 border border-dashed border-o-border rounded-lg text-sm text-o-textSecondary hover:text-o-blueText hover:border-o-blueText/30 transition-colors"
              >
                + Add File
              </button>
            </div>
          )}

          {/* B2: Unified Configuration card */}
          <div className="card">
            <label className="stat-label mb-4 block">Configuration</label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-o-textSecondary">Image</span>
                </div>
                <select
                  value={image}
                  onChange={(e) => setImage(e.target.value)}
                  className="w-full bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text focus:outline-none focus:border-o-blueText"
                >
                  {IMAGES.map((img) => (
                    <option key={img.id} value={img.id}>
                      {img.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-o-muted mt-1">Runtime environment</p>
              </div>
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
            </div>
            <div className="mt-6">
              <span className="text-xs text-o-textSecondary block mb-2">Builder Code (optional)</span>
              <input
                type="text"
                value={builderCode}
                onChange={(e) => setBuilderCode(e.target.value)}
                placeholder="your-builder-code"
                className="w-full sm:w-64 bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText"
              />
              <p className="text-xs text-o-muted mt-1">
                ERC-8021 builder code for dual attribution
              </p>
            </div>
          </div>

          {/* B4: Submit card with live price estimate */}
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
              <div className="flex items-center gap-4 w-full sm:w-auto">
                <div className="text-right">
                  {priceLoading ? (
                    <span className="text-xs text-o-muted">Estimating...</span>
                  ) : priceEstimate ? (
                    <span className="font-mono text-sm text-o-green">{priceEstimate}</span>
                  ) : null}
                </div>
                <button
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  className="w-full sm:w-auto px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {status === "submitting" ? "Preparing..." : status === "paying" ? "Sign Payment..." : "Submit & Pay"}
                </button>
              </div>
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
