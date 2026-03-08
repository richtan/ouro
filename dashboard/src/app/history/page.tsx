"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useWalletReady } from "@/hooks/useWalletReady";
import { useJobEvents } from "@/hooks/useJobEvents";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import OutputDisplay from "@/components/OutputDisplay";
import JobTimeline from "@/components/JobTimeline";
import JobEventFeed from "@/components/JobEventFeed";
import FileBrowser from "@/components/FileBrowser";
import type { WorkspaceFile } from "@/lib/types";

interface ActiveJob {
  id: string;
  slurm_job_id: number | null;
  status: string;
  price_usdc: number;
  submitted_at: string;
  script: string | null;
  mode?: string;
  entrypoint?: string;
  file_count?: number;
  image?: string;
  retry_count?: number;
  failure_reason?: string;
  failure_stage?: number;
  files?: WorkspaceFile[];
}

interface HistoricalJob {
  id: string;
  slurm_job_id: number | null;
  status: string;
  price_usdc: number;
  compute_duration_s: number | null;
  completed_at: string;
  script: string | null;
  output_text: string | null;
  mode?: string;
  entrypoint?: string;
  file_count?: number;
  image?: string;
  failure_reason?: string;
  failure_stage?: number;
  files?: WorkspaceFile[];
}

type AnyJob =
  | (ActiveJob & { _type: "active" })
  | (HistoricalJob & { _type: "historical" });

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  pending: { bg: "bg-o-amber/10", text: "text-o-amber", dot: "bg-o-amber" },
  processing: { bg: "bg-o-blue/10", text: "text-o-blueText", dot: "bg-o-blue" },
  running: { bg: "bg-o-blue/10", text: "text-o-blueText", dot: "bg-o-blue" },
  completed: { bg: "bg-o-green/10", text: "text-o-green", dot: "bg-o-green" },
  failed: { bg: "bg-o-red/10", text: "text-o-red", dot: "bg-o-red" },
};

const IMAGE_LABELS: Record<string, string> = {
  "ouro-ubuntu": "Ubuntu 22.04",
  "ouro-python": "Python 3.12",
  "ouro-nodejs": "Node.js 20",
  // Legacy aliases for historical jobs
  base: "Ubuntu 22.04",
  python312: "Python 3.12",
  node20: "Node.js 20",
  pytorch: "PyTorch",
  "r-base": "R 4.4",
};

function getJobTimestamp(job: AnyJob): Date {
  return job._type === "historical"
    ? new Date((job as HistoricalJob & { _type: "historical" }).completed_at)
    : new Date((job as ActiveJob & { _type: "active" }).submitted_at);
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${status === "running" || status === "processing" ? "animate-pulse" : ""}`} />
      {status}
    </span>
  );
}

function ModeBadge({ mode }: { mode: string }) {
  if (mode !== "multi_file") return null;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider bg-o-blue/10 text-o-blueText">
      multi-file
    </span>
  );
}

function JobCard({ job, expandId, onComplete }: { job: AnyJob; expandId: string | null; onComplete?: () => void }) {
  const [open, setOpen] = useState(job.id === expandId);
  const isHist = job._type === "historical";
  const { events, currentStage } = useJobEvents(
    open ? job.id : null,
    job.status,
  );
  const isTerminal = ["completed", "failed"].includes(job.status) || currentStage >= 4;

  const prevStageRef = useRef(currentStage);
  useEffect(() => {
    if (prevStageRef.current < 4 && currentStage >= 4) {
      onComplete?.();
    }
    prevStageRef.current = currentStage;
  }, [currentStage, onComplete]);
  const hist = isHist ? (job as HistoricalJob & { _type: "historical" }) : null;
  const ts = isHist
    ? new Date(hist!.completed_at).toLocaleString()
    : new Date((job as ActiveJob).submitted_at).toLocaleString();

  return (
    <div className="card">
      <button onClick={() => setOpen(!open)} className="w-full text-left">
        {/* Row 1: ID + status + chevron */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <span className="font-mono text-sm text-o-blueText">{job.id.slice(0, 8)}</span>
            <StatusBadge status={job.status} />
            {!isHist && (job as ActiveJob).retry_count != null && (job as ActiveJob).retry_count! > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-o-amber/10 text-o-amber">
                retry {(job as ActiveJob).retry_count}/2
              </span>
            )}
            {job.mode && <ModeBadge mode={job.mode} />}
          </div>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className={`text-o-muted transition-transform shrink-0 ${open ? "rotate-180" : ""}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
        {/* Row 2: meta info */}
        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
          <span className="font-mono text-xs text-o-green">${(job.price_usdc ?? 0).toFixed(4)}</span>
          {hist?.compute_duration_s != null && (
            <span className="font-mono text-xs text-o-textSecondary">{hist.compute_duration_s.toFixed(1)}s</span>
          )}
          <span className="text-xs text-o-muted">{ts}</span>
          {job.image && job.image !== "base" && (
            <span className="text-xs text-o-muted">{IMAGE_LABELS[job.image] ?? job.image}</span>
          )}
        </div>
      </button>

      {open && (
        <div className="mt-4 pt-4 border-t border-o-border space-y-4">
          {isHist ? (
            <JobTimeline stage={4} failed={job.status === "failed"} failedStage={(job as HistoricalJob).failure_stage} />
          ) : (
            <JobTimeline stage={currentStage} failed={job.status === "failed"} failedStage={job.status === "failed" ? currentStage : undefined} />
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="col-span-2 bg-o-bg rounded-lg p-3 border border-o-border">
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Job ID</div>
              <div className="font-mono text-xs text-o-text break-all">{job.id}</div>
            </div>
            <div className="bg-o-bg rounded-lg p-3 border border-o-border">
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Slurm ID</div>
              <div className="font-mono text-xs text-o-text">{job.slurm_job_id ?? "—"}</div>
            </div>
            <div className="bg-o-bg rounded-lg p-3 border border-o-border">
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Compute Cost</div>
              <div className="font-mono text-xs text-o-green">
                ${(job.price_usdc ?? 0).toFixed(4)}
              </div>
            </div>
          </div>

          {/* Mode-specific details */}
          {job.mode === "multi_file" && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {job.entrypoint && (
                <div className="bg-o-bg rounded-lg p-3 border border-o-border">
                  <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Entrypoint</div>
                  <div className="font-mono text-xs text-o-text">{job.entrypoint}</div>
                </div>
              )}
              {job.file_count != null && (
                <div className="bg-o-bg rounded-lg p-3 border border-o-border">
                  <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Files</div>
                  <div className="font-mono text-xs text-o-text">{job.file_count}</div>
                </div>
              )}
              {job.image && (
                <div className="bg-o-bg rounded-lg p-3 border border-o-border">
                  <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Image</div>
                  <div className="font-mono text-xs text-o-text">{IMAGE_LABELS[job.image] ?? job.image}</div>
                </div>
              )}
            </div>
          )}

          {(() => {
            const outputText = hist?.output_text;
            const failureReason = (job as ActiveJob | HistoricalJob).failure_reason;
            const raw = outputText
              ?? (failureReason ? JSON.stringify({ output: "", error_output: failureReason }) : null);
            if (!raw) return null;
            return (
              <OutputDisplay raw={raw} />
            );
          })()}

          {job.files && job.files.length > 0 ? (
            <FileBrowser files={job.files} />
          ) : job.script ? (
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Script</div>
              <pre className="bg-o-bg border border-o-border rounded-lg p-3 font-mono text-xs text-o-text/80 overflow-x-auto max-h-32 whitespace-pre-wrap">
                {job.script}
              </pre>
            </div>
          ) : null}

          {events.length > 0 && (
            isTerminal ? (
              <details>
                <summary className="text-xs text-o-textSecondary uppercase tracking-wider cursor-pointer hover:text-o-text transition-colors">
                  Event Log
                </summary>
                <div className="mt-2">
                  <JobEventFeed events={events} />
                </div>
              </details>
            ) : (
              <JobEventFeed events={events} />
            )
          )}
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  const searchParams = useSearchParams();
  const expandId = searchParams.get("expand");
  const { address, isConnected, isReady } = useWalletReady();
  const [jobs, setJobs] = useState<AnyJob[]>([]);
  const [loading, setLoading] = useState(false);
  const loadRef = useRef<(() => void) | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    if (!address) return;
    setLoading(true);
    const load = () =>
      fetch(`/api/proxy/jobs?address=${address}`)
        .then((r) => r.json())
        .then((data) => {
          const all: AnyJob[] = [
            ...(data.active ?? []).map((j: ActiveJob) => ({ ...j, _type: "active" as const })),
            ...(data.historical ?? []).map((j: HistoricalJob) => ({ ...j, _type: "historical" as const })),
          ].sort((a, b) => {
            const tsA = a._type === "historical"
              ? new Date((a as HistoricalJob & { _type: "historical" }).completed_at).getTime()
              : new Date((a as ActiveJob & { _type: "active" }).submitted_at).getTime();
            const tsB = b._type === "historical"
              ? new Date((b as HistoricalJob & { _type: "historical" }).completed_at).getTime()
              : new Date((b as ActiveJob & { _type: "active" }).submitted_at).getTime();
            return tsB - tsA;
          });
          setJobs(all);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    loadRef.current = load;
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [address]);

  const isFiltering = search !== "" || dateFrom !== "" || dateTo !== "";

  const filtered = isFiltering
    ? jobs.filter((job) => {
        if (search) {
          const q = search.toLowerCase();
          const id = job.id.toLowerCase();
          const status = job.status.toLowerCase();
          const image = (IMAGE_LABELS[job.image ?? ""] ?? job.image ?? "").toLowerCase();
          const slurmId = job.slurm_job_id != null ? String(job.slurm_job_id) : "";
          if (!id.includes(q) && !status.includes(q) && !image.includes(q) && !slurmId.includes(q)) {
            return false;
          }
        }
        if (dateFrom || dateTo) {
          const ts = getJobTimestamp(job);
          if (dateFrom && ts < new Date(dateFrom + "T00:00:00")) return false;
          if (dateTo) {
            const end = new Date(dateTo + "T00:00:00");
            end.setDate(end.getDate() + 1);
            if (ts >= end) return false;
          }
        }
        return true;
      })
    : jobs;

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          My Jobs
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          View all compute jobs submitted from your wallet
        </p>
      </div>

      {!isReady ? (
        <div className="card animate-pulse"><div className="h-32 bg-o-border/30 rounded" /></div>
      ) : !isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">Connect your wallet to view your job history</p>
          <ConnectButton />
        </div>
      ) : loading && jobs.length === 0 ? (
        <div className="card animate-pulse">
          <div className="h-32 bg-o-border/30 rounded" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="card text-center py-16">
          <p className="text-o-textSecondary text-sm mb-4">No jobs found for this wallet</p>
          <a
            href="/submit"
            className="inline-block px-6 py-3 bg-o-blue text-white border border-o-blue rounded-lg text-sm font-medium hover:bg-o-blueHover transition-colors"
          >
            Submit your first job &rarr;
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="pb-4 mb-1 border-b border-o-border">
            <div className="flex items-start justify-between gap-4">
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="font-display text-base font-semibold text-o-text">
                    {isFiltering ? `${filtered.length} of ${jobs.length}` : jobs.length} <span className="text-sm font-normal text-o-textSecondary">job{jobs.length !== 1 ? "s" : ""}</span>
                  </span>
                  <span className="text-o-textSecondary">·</span>
                  <span className="font-mono text-sm text-o-blueText truncate">
                    <span className="md:hidden">{address?.slice(0, 6)}...{address?.slice(-4)}</span>
                    <span className="hidden md:inline">{address}</span>
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-o-green/10 text-o-green">
                    <span className="w-1.5 h-1.5 rounded-full bg-o-green" />
                    {jobs.filter(j => j.status === "completed").length} completed
                  </span>
                  {jobs.some(j => j.status === "failed") && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-o-red/10 text-o-red">
                      <span className="w-1.5 h-1.5 rounded-full bg-o-red" />
                      {jobs.filter(j => j.status === "failed").length} failed
                    </span>
                  )}
                  {jobs.some(j => ["pending", "processing", "running"].includes(j.status)) && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-o-amber/10 text-o-amber">
                      <span className="w-1.5 h-1.5 rounded-full bg-o-amber animate-pulse" />
                      {jobs.filter(j => ["pending", "processing", "running"].includes(j.status)).length} active
                    </span>
                  )}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-xs text-o-textSecondary uppercase tracking-wider">Total Spent</div>
                <div className="font-mono text-lg font-semibold text-o-green mt-0.5">${jobs.reduce((s, j) => s + (j.price_usdc ?? 0), 0).toFixed(4)}</div>
              </div>
            </div>
          </div>
          {/* Filter bar */}
          <div className="flex flex-col sm:flex-row gap-2 mb-3">
            <div className="relative flex-1">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-o-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by ID, status, image..."
                className="w-full bg-o-bg border border-o-border rounded-lg pl-9 pr-3 py-2.5 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText"
              />
            </div>
            <div className="flex gap-2 mt-1 sm:mt-0">
              <div className="relative">
                <span className="absolute -top-[5px] left-2 px-1 text-[10px] leading-none text-o-muted uppercase tracking-wider bg-o-bg">From</span>
                <input
                  type="date"
                  value={dateFrom}
                  max={dateTo || undefined}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-[140px] bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text focus:outline-none focus:border-o-blueText"
                  style={{ colorScheme: "dark" }}
                />
              </div>
              <div className="relative">
                <span className="absolute -top-[5px] left-2 px-1 text-[10px] leading-none text-o-muted uppercase tracking-wider bg-o-bg">To</span>
                <input
                  type="date"
                  value={dateTo}
                  min={dateFrom || undefined}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-[140px] bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text focus:outline-none focus:border-o-blueText"
                  style={{ colorScheme: "dark" }}
                />
              </div>
            </div>
          </div>
          {filtered.map((job) => (
            <JobCard key={job.id} job={job} expandId={expandId} onComplete={() => loadRef.current?.()} />
          ))}
          {filtered.length === 0 && isFiltering && (
            <div className="text-center py-8">
              <p className="text-o-textSecondary text-sm">No jobs match your filters</p>
              <button
                onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); }}
                className="mt-2 text-xs text-o-blueText hover:underline"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
