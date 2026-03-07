"use client";

import { useEffect, useState } from "react";
import { fetchJobs } from "@/lib/api";
import OutputDisplay from "@/components/OutputDisplay";

interface Job {
  id: string;
  slurm_job_id: number | null;
  status: string;
  price_usdc: number;
  gas_paid_usd: number | null;
  proof_tx_hash: string | null;
  compute_duration_s: number | null;
  submitted_at: string;
  completed_at: string | null;
  script: string | null;
  output_text: string | null;
  submitter_address: string | null;
  retry_count: number | null;
  mode?: string;
  entrypoint?: string;
  file_count?: number;
  image?: string;
}

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

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${status === "running" || status === "processing" ? "animate-pulse" : ""}`} />
      {status}
    </span>
  );
}

function JobRow({ job }: { job: Job }) {
  const [open, setOpen] = useState(false);
  const ts = job.completed_at
    ? new Date(job.completed_at).toLocaleString()
    : new Date(job.submitted_at).toLocaleString();

  return (
    <>
      {/* Desktop row */}
      <button
        onClick={() => setOpen(!open)}
        className="hidden md:grid grid-cols-[minmax(0,1fr)_80px_100px_80px_80px_140px_24px] gap-2 items-center w-full px-3 py-2.5 text-left hover:bg-o-surfaceHover transition-colors rounded-lg"
      >
        <span className="font-mono text-xs text-o-blueText truncate">{job.id.slice(0, 12)}</span>
        <span className="font-mono text-xs text-o-muted">{job.slurm_job_id ?? "—"}</span>
        <span className="flex items-center gap-1.5">
          <StatusBadge status={job.status} />
          {job.mode === "multi_file" && (
            <span className="text-[10px] text-o-blueText bg-o-blue/10 px-1 py-0.5 rounded">MF</span>
          )}
        </span>
        <span className="font-mono text-xs text-o-green text-right">${(job.price_usdc ?? 0).toFixed(4)}</span>
        <span className="font-mono text-xs text-o-textSecondary text-right">
          {job.compute_duration_s != null ? `${job.compute_duration_s.toFixed(1)}s` : "—"}
        </span>
        <span className="text-xs text-o-muted text-right">{ts}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`text-o-muted transition-transform ${open ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Mobile card */}
      <button
        onClick={() => setOpen(!open)}
        className="md:hidden w-full text-left bg-o-bg rounded-lg border border-o-border p-3 hover:border-o-borderHover transition-colors"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-mono text-xs text-o-blueText">{job.id.slice(0, 8)}</span>
            <StatusBadge status={job.status} />
            {job.mode === "multi_file" && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider bg-o-blue/10 text-o-blueText">
                multi-file
              </span>
            )}
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
        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
          <span className="font-mono text-xs text-o-green">${(job.price_usdc ?? 0).toFixed(4)}</span>
          {job.compute_duration_s != null && (
            <span className="font-mono text-xs text-o-textSecondary">{job.compute_duration_s.toFixed(1)}s</span>
          )}
          <span className="text-xs text-o-muted">{ts}</span>
          {job.image && job.image !== "base" && (
            <span className="text-xs text-o-muted">{IMAGE_LABELS[job.image] ?? job.image}</span>
          )}
        </div>
      </button>

      {open && (
        <div className="bg-o-bg rounded-lg border border-o-border p-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Job ID</div>
              <div className="font-mono text-xs text-o-text break-all">{job.id}</div>
            </div>
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Slurm ID</div>
              <div className="font-mono text-xs text-o-text">{job.slurm_job_id ?? "—"}</div>
            </div>
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Submitter</div>
              <div className="font-mono text-xs text-o-text truncate">{job.submitter_address ?? "—"}</div>
            </div>
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Gas</div>
              <div className="font-mono text-xs text-o-red">${(job.gas_paid_usd ?? 0).toFixed(6)}</div>
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

          {job.retry_count != null && job.retry_count > 0 && (
            <div className="text-xs text-o-amber">
              Retries: {job.retry_count}
            </div>
          )}
          {job.proof_tx_hash && (
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Proof TX</div>
              <a
                href={`https://basescan.org/tx/${job.proof_tx_hash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs text-o-blueText hover:underline"
              >
                {job.proof_tx_hash.slice(0, 14)}...{job.proof_tx_hash.slice(-8)}
              </a>
            </div>
          )}
          {job.script && (
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Script</div>
              <pre className="bg-o-surface border border-o-border rounded-lg p-3 font-mono text-xs text-o-text/80 overflow-x-auto max-h-32 whitespace-pre-wrap">
                {job.script}
              </pre>
            </div>
          )}
          {job.output_text && (
            <div>
              <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-2">Output</div>
              <OutputDisplay raw={job.output_text} />
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function JobsPanel() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      fetchJobs()
        .then((data) => {
          const all = [
            ...(data.active ?? []).map((j: Job) => ({ ...j })),
            ...(data.historical ?? []).map((j: Job) => ({ ...j })),
          ].sort((a, b) => {
            const tsA = new Date(a.completed_at ?? a.submitted_at).getTime();
            const tsB = new Date(b.completed_at ?? b.submitted_at).getTime();
            return tsB - tsA;
          });
          setJobs(all);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    load();
    const id = setInterval(load, 5_000);
    return () => clearInterval(id);
  }, []);

  if (loading && jobs.length === 0) {
    return (
      <div className="card animate-pulse">
        <div className="h-48 bg-o-border/30 rounded" />
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="stat-label">All Jobs (Admin)</div>
        <span className="text-xs text-o-textSecondary">{jobs.length} total</span>
      </div>

      {/* Desktop column headers */}
      <div className="hidden md:grid grid-cols-[minmax(0,1fr)_80px_100px_80px_80px_140px_24px] gap-2 px-3 py-2 text-xs text-o-muted uppercase tracking-wider border-b border-o-border mb-1">
        <span>ID</span>
        <span>Slurm</span>
        <span>Status</span>
        <span className="text-right">Price</span>
        <span className="text-right">Duration</span>
        <span className="text-right">Time</span>
        <span />
      </div>

      <div className="space-y-1 max-h-[600px] overflow-y-auto">
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} />
        ))}
      </div>
    </div>
  );
}
