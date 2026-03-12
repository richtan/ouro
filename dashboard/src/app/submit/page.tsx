"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useWalletClient, usePublicClient } from "wagmi";
import { useWalletReady } from "@/hooks/useWalletReady";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { x402Client } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { wrapFetchWithPayment } from "@x402/fetch";
import FileExplorer from "@/components/submit/FileExplorer";
import StickySubmitBar from "@/components/submit/StickySubmitBar";
import EnvironmentPicker, { DEFAULT_FILES } from "@/components/submit/EnvironmentPicker";
import { parseDockerfile } from "@/lib/dockerfile";
import type { WorkspaceFile } from "@/lib/types";

function StepperPill({
  value,
  onChange,
  min,
  max,
  suffix,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  suffix?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = () => {
    const n = parseInt(draft, 10);
    onChange(Number.isNaN(n) ? min : Math.min(max, Math.max(min, n)));
    setEditing(false);
  };

  return (
    <div className="bg-o-bg border border-o-border rounded-full px-1 flex items-center gap-0">
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="text-o-textSecondary hover:text-o-text px-2 py-1.5 text-sm font-mono select-none"
      >
        &ndash;
      </button>
      {editing ? (
        <input
          ref={inputRef}
          type="number"
          min={min}
          max={max}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && commit()}
          className="w-10 text-center bg-transparent font-mono text-sm text-o-text outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
      ) : (
        <button
          type="button"
          onClick={() => {
            setDraft(String(value));
            setEditing(true);
          }}
          className="font-mono text-sm text-o-text px-1 min-w-[2rem] text-center"
        >
          {value}
          {suffix ?? ""}
        </button>
      )}
      <button
        type="button"
        onClick={() => onChange(Math.min(max, value + 1))}
        className="text-o-textSecondary hover:text-o-text px-2 py-1.5 text-sm font-mono select-none"
      >
        +
      </button>
    </div>
  );
}

type JobStatus = "idle" | "submitting" | "paying" | "error";

export default function SubmitPage() {
  const router = useRouter();
  const { address, isConnected, isReady } = useWalletReady();
  const { data: walletClient } = useWalletClient();
  const publicClient = usePublicClient();

  const [files, setFiles] = useState<WorkspaceFile[]>(DEFAULT_FILES);
  const [cpus, setCpus] = useState(1);
  const [timeLimit, setTimeLimit] = useState(1);
  const [builderCode, setBuilderCode] = useState("");
  const [status, setStatus] = useState<JobStatus>("idle");
  const [error, setError] = useState("");
  const [priceEstimate, setPriceEstimate] = useState<string | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [creditBalance, setCreditBalance] = useState(0);

  // Fetch credit balance when wallet connects
  useEffect(() => {
    if (!address) return;
    fetch(`/api/proxy/credits?address=${address}`)
      .then((r) => r.json())
      .then((data) => setCreditBalance(data.available ?? 0))
      .catch(() => {});
  }, [address]);

  // Parse Dockerfile from files
  const dockerfileInfo = useMemo(() => {
    const df = files.find((f) => f.path?.toLowerCase() === "dockerfile");
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

  const validationErrors = useMemo(() => {
    const errors: string[] = [];
    if (!files.length) {
      errors.push("No files");
      return errors;
    }
    const emptyFiles = files.filter((f) => !(f.path ?? "").trim() || !(f.content ?? "").trim());
    if (emptyFiles.length) {
      errors.push("Some files are empty or unnamed");
    }
    if (dockerfileInfo) {
      errors.push(...dockerfileInfo.errors);
    } else {
      errors.push("Missing Dockerfile");
    }
    return errors;
  }, [files, dockerfileInfo]);

  const canSubmit =
    status !== "submitting" &&
    status !== "paying" &&
    files.length > 0 &&
    files.every((f) => (f.path ?? "").trim() && (f.content ?? "").trim()) &&
    dockerfileInfo?.isValid === true;

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto pb-24">
      {/* Header */}
      <div className="mb-8">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-2 md:gap-4">
          <div>
            <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
              Submit Job
            </h1>
            <p className="font-body text-sm text-o-textSecondary mt-1">
              Write code, configure resources, pay with USDC
            </p>
          </div>
          {creditBalance > 0 && isConnected && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-o-amber/10 text-o-amber md:mt-1 self-start">
              ${creditBalance.toFixed(4)} credit available
            </span>
          )}
        </div>
      </div>

      {!isReady ? (
        <div className="card animate-pulse"><div className="h-32 bg-o-border/30 rounded" /></div>
      ) : !isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">
            Connect your wallet to submit compute jobs
          </p>
          <ConnectButton />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Configuration */}
          <div className="border border-o-border rounded-xl p-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-o-textSecondary">CPUs</span>
                <StepperPill value={cpus} onChange={setCpus} min={1} max={8} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-o-textSecondary">Time Limit (min)</span>
                <StepperPill value={timeLimit} onChange={setTimeLimit} min={1} max={60} />
              </div>
            </div>

            {/* Advanced toggle */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1.5 mt-3 pt-3 border-t border-o-border text-xs text-o-textSecondary hover:text-o-text transition-colors w-full"
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                className={`transition-transform ${showAdvanced ? "rotate-90" : ""}`}
              >
                <path
                  d="M3 1.5L7 5L3 8.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Advanced
            </button>
            {showAdvanced && (
              <div className="mt-3">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm text-o-textSecondary whitespace-nowrap">Builder Code</span>
                  <input
                    type="text"
                    value={builderCode}
                    onChange={(e) => setBuilderCode(e.target.value)}
                    placeholder="your-builder-code"
                    className="w-full sm:w-64 bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText"
                  />
                </div>
                <p className="text-xs text-o-muted mt-1 text-right">
                  ERC-8021 builder code for dual attribution
                </p>
              </div>
            )}
          </div>

          {/* Environment Picker */}
          <EnvironmentPicker
            onSelect={setFiles}
            currentFromImage={dockerfileInfo?.fromImage ?? null}
          />

          {/* File Explorer */}
          <FileExplorer
            files={files}
            onFilesChange={setFiles}
            defaultImage={dockerfileInfo?.fromImage ?? "base"}
            height="400px"
          />
        </div>
      )}

      {/* Sticky submit bar */}
      {isReady && isConnected && (
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
          validationErrors={validationErrors}
          creditBalance={creditBalance}
        />
      )}
    </main>
  );
}
