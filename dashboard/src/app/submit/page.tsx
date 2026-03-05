"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAccount, useWalletClient, usePublicClient } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { x402Client } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { wrapFetchWithPayment } from "@x402/fetch";
import FileExplorer from "@/components/submit/FileExplorer";
import StickySubmitBar from "@/components/submit/StickySubmitBar";
import { parseDockerfile } from "@/lib/dockerfile";

type JobStatus = "idle" | "submitting" | "paying" | "error";

interface WorkspaceFile {
  path: string;
  content: string;
}

const TEMPLATES = [
  {
    name: "Hello World",
    desc: "Echo + hostname + uptime",
    files: [
      { path: "Dockerfile", content: 'FROM base\nENTRYPOINT ["bash", "job.sh"]' },
      { path: "job.sh", content: '#!/bin/bash\necho "Hello from Ouro HPC cluster!"\nhostname && uptime' },
    ],
  },
  {
    name: "Python Math",
    desc: "Compute 100! with stdlib",
    files: [
      { path: "Dockerfile", content: 'FROM python312\nENTRYPOINT ["python", "main.py"]' },
      { path: "main.py", content: '#!/usr/bin/env python3\nimport math\nprint(f"100! = {math.factorial(100)}")' },
    ],
  },
  {
    name: "Python + Deps",
    desc: "Pandas data analysis",
    files: [
      { path: "Dockerfile", content: 'FROM python312\nRUN pip install pandas numpy\nENTRYPOINT ["python", "analysis.py"]' },
      { path: "analysis.py", content: 'import pandas as pd\nimport numpy as np\ndf = pd.DataFrame(np.random.randn(100, 4), columns=list("ABCD"))\nprint(df.describe())' },
    ],
  },
  {
    name: "System Info",
    desc: "CPU, memory, disk, uptime",
    files: [
      { path: "Dockerfile", content: 'FROM base\nENTRYPOINT ["bash", "job.sh"]' },
      { path: "job.sh", content: "#!/bin/bash\necho '=== CPU ==='\nnproc\necho '=== Memory ==='\nfree -h 2>/dev/null || echo 'N/A'\necho '=== Disk ==='\ndf -h / 2>/dev/null\necho '=== Uptime ==='\nuptime" },
    ],
  },
];

export default function SubmitPage() {
  const router = useRouter();
  const { address, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();
  const publicClient = usePublicClient();

  const [files, setFiles] = useState<WorkspaceFile[]>(TEMPLATES[0].files);
  const [cpus, setCpus] = useState(1);
  const [timeLimit, setTimeLimit] = useState(1);
  const [builderCode, setBuilderCode] = useState("");
  const [status, setStatus] = useState<JobStatus>("idle");
  const [error, setError] = useState("");
  const [priceEstimate, setPriceEstimate] = useState<string | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [activeTemplate, setActiveTemplate] = useState(0);

  // Parse Dockerfile from files
  const dockerfileInfo = useMemo(() => {
    const df = files.find((f) => f.path.toLowerCase() === "dockerfile");
    return df ? parseDockerfile(df.content) : null;
  }, [files]);

  // Live price estimate — debounced
  useEffect(() => {
    setPriceLoading(true);
    const timeout = setTimeout(() => {
      fetch(
        `/api/proxy/price?cpus=${cpus}&time_limit_min=${timeLimit}&submission_mode=multi_file`,
      )
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
  }, [cpus, timeLimit]);

  // Submit handler
  const handleSubmit = async () => {
    if (!walletClient || !publicClient || !isConnected) return;
    setStatus("submitting");
    setError("");

    try {
      const signer = toClientEvmSigner(
        {
          address: walletClient.account.address,
          signTypedData: (args: Record<string, unknown>) =>
            walletClient.signTypedData(
              args as Parameters<typeof walletClient.signTypedData>[0],
            ),
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

      const body = {
        files: files.map((f) => ({ path: f.path, content: f.content })),
        cpus,
        time_limit_min: timeLimit,
        submitter_address: address,
      };

      const res = await fetchWithPay("/api/proxy/submit", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const respBody = await res.json().catch(() => ({}));
        throw new Error(
          respBody.detail || respBody.error || `HTTP ${res.status}`,
        );
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
    files.length > 0 &&
    files.every((f) => f.path.trim() && f.content.trim()) &&
    dockerfileInfo?.isValid === true;

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto pb-24">
      {/* Header */}
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Submit Compute Job
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Write code, configure resources, pay with USDC
        </p>
      </div>

      {!isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">
            Connect your wallet to submit compute jobs
          </p>
          <ConnectButton />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Templates */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {TEMPLATES.map((t, i) => (
              <button
                key={t.name}
                onClick={() => {
                  setFiles(t.files);
                  setActiveTemplate(i);
                }}
                className={`bg-o-bg border rounded-lg px-3 py-2.5 text-left transition-colors ${
                  activeTemplate === i
                    ? "border-o-blueText bg-o-blue/5"
                    : "border-o-border hover:border-o-blueText/30"
                }`}
              >
                <div className="text-sm font-medium text-o-text">
                  {t.name}
                </div>
                <div className="text-xs text-o-muted mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>

          {/* File Explorer */}
          <FileExplorer
            files={files}
            onFilesChange={setFiles}
            defaultImage={dockerfileInfo?.fromImage ?? "base"}
            height="400px"
          />

          {/* Configuration */}
          <div className="card">
            <label className="stat-label mb-4 block">Configuration</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-o-textSecondary">CPUs</span>
                  <span className="font-mono text-sm text-o-blueText">
                    {cpus}
                  </span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={8}
                  value={cpus}
                  onChange={(e) => setCpus(Number(e.target.value))}
                  className="w-full accent-o-blue"
                />
                <div className="flex justify-between text-xs text-o-muted mt-1">
                  <span>1</span>
                  <span>8</span>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-o-textSecondary">
                    Time Limit
                  </span>
                  <span className="font-mono text-sm text-o-blueText">
                    {timeLimit}m
                  </span>
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
              <span className="text-xs text-o-textSecondary block mb-2">
                Builder Code (optional)
              </span>
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
        </div>
      )}

      {/* Sticky submit bar */}
      {isConnected && (
        <StickySubmitBar
          fromImage={dockerfileInfo?.fromImage ?? null}
          entrypointDisplay={dockerfileInfo?.entrypoint ?? null}
          cpus={cpus}
          timeLimit={timeLimit}
          priceEstimate={priceEstimate}
          priceLoading={priceLoading}
          canSubmit={canSubmit}
          isConnected={isConnected}
          status={status}
          onSubmit={handleSubmit}
          error={status === "error" ? error : null}
        />
      )}
    </main>
  );
}
