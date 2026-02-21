"use client";

import { useEffect, useState } from "react";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import OutputDisplay from "@/components/OutputDisplay";

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

type AnyJob =
  | (ActiveJob & { _type: "active" })
  | (HistoricalJob & { _type: "historical" });

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  pending: { bg: "bg-amber-500/10", text: "text-amber-400", dot: "bg-amber-400" },
  processing: { bg: "bg-blue-500/10", text: "text-blue-400", dot: "bg-blue-400" },
  running: { bg: "bg-blue-500/10", text: "text-blue-400", dot: "bg-blue-400" },
  completed: { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  failed: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
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

function JobCard({ job }: { job: AnyJob }) {
  const [open, setOpen] = useState(false);
  const isHist = job._type === "historical";
  const hist = isHist ? (job as HistoricalJob & { _type: "historical" }) : null;
  const ts = isHist
    ? new Date(hist!.completed_at).toLocaleString()
    : new Date((job as ActiveJob).submitted_at).toLocaleString();

  return (
    <div className="card">
      <button onClick={() => setOpen(!open)} className="w-full text-left">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <span className="font-mono text-sm text-ouro-accent">{job.id.slice(0, 8)}</span>
            <StatusBadge status={job.status} />
          </div>
          <div className="flex items-center gap-4 shrink-0">
            <span className="font-mono text-sm text-ouro-green">${(job.price_usdc ?? 0).toFixed(4)}</span>
            {hist?.compute_duration_s != null && (
              <span className="font-mono text-xs text-ouro-muted">{hist.compute_duration_s.toFixed(1)}s</span>
            )}
            <span className="text-xs text-ouro-muted">{ts}</span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={`text-ouro-muted transition-transform ${open ? "rotate-180" : ""}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-4 pt-4 border-t border-ouro-border/30 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Job ID</div>
              <div className="font-mono text-xs text-ouro-text break-all">{job.id}</div>
            </div>
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Slurm ID</div>
              <div className="font-mono text-xs text-ouro-text">{job.slurm_job_id ?? "—"}</div>
            </div>
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Price</div>
              <div className="font-mono text-xs text-ouro-green">${(job.price_usdc ?? 0).toFixed(6)}</div>
            </div>
            {hist?.gas_paid_usd != null && (
              <div>
                <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-1">Gas</div>
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
              <pre className="bg-black/40 border border-ouro-border/30 rounded p-3 font-mono text-xs text-ouro-text/80 overflow-x-auto max-h-32 whitespace-pre-wrap">
                {job.script}
              </pre>
            </div>
          )}

          {hist?.output_text && (
            <div>
              <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-2">
                Output <span className="text-ouro-green normal-case tracking-normal ml-1">from Slurm cluster</span>
              </div>
              <OutputDisplay raw={hist.output_text} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  const { address, isConnected } = useAccount();
  const [jobs, setJobs] = useState<AnyJob[]>([]);
  const [loading, setLoading] = useState(false);

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
          ];
          setJobs(all);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [address]);

  return (
    <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
          My Jobs
        </h1>
        <p className="font-body text-sm text-ouro-muted mt-1">
          View all compute jobs submitted from your wallet
        </p>
      </div>

      {!isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-ouro-muted text-sm">Connect your wallet to view your job history</p>
          <ConnectButton />
        </div>
      ) : loading && jobs.length === 0 ? (
        <div className="card animate-pulse">
          <div className="h-32 bg-ouro-border/30 rounded" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="card text-center py-16">
          <p className="text-ouro-muted text-sm mb-4">No jobs found for this wallet</p>
          <a
            href="/submit"
            className="inline-block px-4 py-2 bg-ouro-accent/10 text-ouro-accent border border-ouro-accent/20 rounded text-xs font-mono hover:bg-ouro-accent/20 transition-colors"
          >
            Submit your first job &rarr;
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-ouro-muted font-mono">
              {jobs.length} job{jobs.length !== 1 ? "s" : ""} for {address?.slice(0, 6)}...{address?.slice(-4)}
            </span>
            <span className="text-xs text-ouro-muted font-mono">
              Total: ${jobs.reduce((s, j) => s + (j.price_usdc ?? 0), 0).toFixed(4)}
            </span>
          </div>
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </main>
  );
}
