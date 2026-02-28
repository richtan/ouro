"use client";

import { useEffect, useState } from "react";
import { fetchJobs } from "@/lib/api";
import OutputDisplay from "./OutputDisplay";

interface ActiveJob {
  id: string;
  slurm_job_id: number | null;
  status: string;
  price_usdc: number;
  submitted_at: string;
  script: string | null;
}

interface HistoricalJob {
  id: string;
  slurm_job_id: number | null;
  status: string;
  price_usdc: number;
  gas_paid_usd: number | null;
  proof_tx_hash: string | null;
  compute_duration_s: number | null;
  completed_at: string;
  script: string | null;
  output_text: string | null;
}

interface JobsData {
  active: ActiveJob[];
  historical: HistoricalJob[];
}

type AnyJob = (ActiveJob & { _type: "active" }) | (HistoricalJob & { _type: "historical" });

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  pending: { bg: "bg-amber-500/10", text: "text-amber-400", dot: "bg-amber-400" },
  processing: { bg: "bg-blue-500/10", text: "text-blue-400", dot: "bg-blue-400" },
  running: { bg: "bg-blue-500/10", text: "text-blue-400", dot: "bg-blue-400" },
  completed: { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  failed: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
  error: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-mono ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${status === "running" || status === "processing" ? "animate-pulse" : ""}`} />
      {status}
    </span>
  );
}

function JobRow({ job, expanded, onToggle }: { job: AnyJob; expanded: boolean; onToggle: () => void }) {
  const isHist = job._type === "historical";
  const hist = isHist ? (job as HistoricalJob & { _type: "historical" }) : null;

  const timestamp = isHist
    ? new Date(hist!.completed_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
    : new Date((job as ActiveJob).submitted_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

  const scriptPreview = job.script ? job.script.replace(/^#!.*\n/, "").trim().slice(0, 60) : "—";

  return (
    <div className="border border-ouro-border/40 rounded-lg overflow-hidden transition-colors hover:border-ouro-border/70">
      <button
        onClick={onToggle}
        className="w-full grid grid-cols-[minmax(0,1fr)_80px_minmax(0,2fr)_80px_80px_80px] gap-3 items-center px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <span className="font-mono text-xs text-ouro-accent truncate">{job.id.slice(0, 8)}</span>
        <StatusBadge status={job.status} />
        <span className="font-mono text-xs text-ouro-muted truncate">{scriptPreview}</span>
        <span className="font-mono text-xs text-ouro-text text-right">
          {hist?.compute_duration_s != null ? `${hist.compute_duration_s.toFixed(1)}s` : "—"}
        </span>
        <span className="font-mono text-xs text-ouro-green text-right">${job.price_usdc.toFixed(4)}</span>
        <span className="text-xs text-ouro-muted text-right">{timestamp.split(", ").pop()}</span>
      </button>

      {expanded && (
        <div className="border-t border-ouro-border/30 bg-black/20 px-4 py-4 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Job ID</div>
              <div className="font-mono text-xs text-ouro-text break-all">{job.id}</div>
            </div>
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Slurm Job ID</div>
              <div className="font-mono text-xs text-ouro-text">{job.slurm_job_id ?? "—"}</div>
            </div>
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Price Paid</div>
              <div className="font-mono text-xs text-ouro-green">${job.price_usdc.toFixed(6)}</div>
            </div>
            {hist?.gas_paid_usd != null && (
              <div>
                <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Gas Cost</div>
                <div className="font-mono text-xs text-ouro-red">${hist.gas_paid_usd.toFixed(6)}</div>
              </div>
            )}
          </div>

          {hist?.proof_tx_hash && (
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">On-Chain Proof</div>
              <a
                href={`https://basescan.org/tx/${hist.proof_tx_hash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 font-mono text-xs text-ouro-accent hover:underline"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                  <polyline points="15 3 21 3 21 9" />
                  <line x1="10" y1="14" x2="21" y2="3" />
                </svg>
                {hist.proof_tx_hash.slice(0, 14)}...{hist.proof_tx_hash.slice(-8)}
              </a>
            </div>
          )}

          {job.script && (
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Script</div>
              <pre className="bg-black/40 border border-ouro-border/30 rounded p-3 font-mono text-xs text-ouro-text/80 overflow-x-auto max-h-32 whitespace-pre-wrap">{job.script}</pre>
            </div>
          )}

          {hist?.output_text && (
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-2">
                Output
                <span className="text-ouro-green ml-2 normal-case tracking-normal">from Slurm cluster</span>
              </div>
              <OutputDisplay raw={hist.output_text} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function JobsPanel() {
  const [jobs, setJobs] = useState<JobsData | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    const load = () => fetchJobs().then(setJobs).catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!jobs) {
    return (
      <div className="card animate-pulse">
        <div className="h-48 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  const allJobs: AnyJob[] = [
    ...(jobs.active ?? []).map((j) => ({ ...j, _type: "active" as const })),
    ...(jobs.historical ?? []).map((j) => ({ ...j, _type: "historical" as const })),
  ].sort((a, b) => {
    const tsA = a._type === "historical"
      ? new Date((a as HistoricalJob & { _type: "historical" }).completed_at).getTime()
      : new Date((a as ActiveJob & { _type: "active" }).submitted_at).getTime();
    const tsB = b._type === "historical"
      ? new Date((b as HistoricalJob & { _type: "historical" }).completed_at).getTime()
      : new Date((b as ActiveJob & { _type: "active" }).submitted_at).getTime();
    return tsB - tsA;
  });

  const completed = (jobs.historical ?? []).length;
  const active = (jobs.active ?? []).length;
  const totalRevenue = (jobs.historical ?? []).reduce((s, j) => s + (j.price_usdc ?? 0), 0);
  const avgDuration =
    completed > 0
      ? (jobs.historical ?? []).reduce((s, j) => s + (j.compute_duration_s ?? 0), 0) / completed
      : 0;

  return (
    <div className="card col-span-full animate-slide-up">
      <div className="flex items-center justify-between mb-5">
        <div className="stat-label">Compute Jobs</div>
        <div className="flex items-center gap-1.5 text-xs text-ouro-muted">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ouro-accent">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          GCP Slurm Cluster
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Active</div>
          <div className="font-display text-xl font-bold text-ouro-amber mt-1">{active}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Completed</div>
          <div className="font-display text-xl font-bold text-ouro-green mt-1">{completed}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Total Revenue</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">${totalRevenue.toFixed(4)}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Avg Duration</div>
          <div className="font-display text-xl font-bold text-ouro-accent mt-1">{avgDuration.toFixed(1)}s</div>
        </div>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[minmax(0,1fr)_80px_minmax(0,2fr)_80px_80px_80px] gap-3 px-4 pb-2 text-[10px] text-ouro-muted uppercase tracking-wider">
        <span>ID</span>
        <span>Status</span>
        <span>Script</span>
        <span className="text-right">Duration</span>
        <span className="text-right">Price</span>
        <span className="text-right">Time</span>
      </div>

      <div className="space-y-1.5 max-h-[480px] overflow-y-auto">
        {allJobs.length === 0 && (
          <div className="text-center py-8 text-sm text-ouro-muted">No jobs yet. Submit a compute request to get started.</div>
        )}
        {allJobs.map((job) => (
          <JobRow
            key={job.id}
            job={job}
            expanded={expandedId === job.id}
            onToggle={() => setExpandedId(expandedId === job.id ? null : job.id)}
          />
        ))}
      </div>
    </div>
  );
}
