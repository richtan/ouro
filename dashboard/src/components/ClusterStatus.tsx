"use client";

import { useEffect, useState } from "react";
import { fetchJobs } from "@/lib/api";

interface JobsData {
  active: {
    id: string;
    slurm_job_id: number | null;
    status: string;
    price_usdc: number;
    submitted_at: string;
  }[];
  historical: {
    id: string;
    status: string;
    price_usdc: number;
    compute_duration_s: number | null;
    completed_at: string;
  }[];
}

export default function ClusterStatus() {
  const [jobs, setJobs] = useState<JobsData | null>(null);

  useEffect(() => {
    const load = () => fetchJobs().then(setJobs).catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!jobs) {
    return (
      <div className="card animate-pulse">
        <div className="h-40 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  const completed = jobs.historical.length;
  const active = jobs.active.length;
  const avgDuration =
    completed > 0
      ? jobs.historical.reduce((sum, j) => sum + (j.compute_duration_s ?? 0), 0) / completed
      : 0;

  return (
    <div className="card animate-slide-up">
      <div className="stat-label mb-4">Cluster & Jobs</div>

      <div className="grid grid-cols-3 gap-4 mb-5">
        <div className="text-center">
          <div className="stat-value text-ouro-green">{active}</div>
          <div className="stat-label">Active</div>
        </div>
        <div className="text-center">
          <div className="stat-value text-ouro-text">{completed}</div>
          <div className="stat-label">Completed</div>
        </div>
        <div className="text-center">
          <div className="stat-value text-ouro-accent">{avgDuration.toFixed(1)}s</div>
          <div className="stat-label">Avg Time</div>
        </div>
      </div>

      <div className="space-y-2 max-h-40 overflow-y-auto">
        <div className="stat-label mb-1">Recent Jobs</div>
        {jobs.active.map((j) => (
          <div
            key={j.id}
            className="flex items-center justify-between text-xs bg-black/20 rounded px-2.5 py-1.5 border border-ouro-border/30"
          >
            <span className="font-mono text-ouro-accent">{j.id.slice(0, 8)}</span>
            <span className="text-ouro-amber uppercase text-[10px] tracking-wider">
              {j.status}
            </span>
            <span className="font-mono text-ouro-muted">${j.price_usdc.toFixed(4)}</span>
          </div>
        ))}
        {jobs.historical.slice(0, 5).map((j) => (
          <div
            key={j.id}
            className="flex items-center justify-between text-xs bg-black/20 rounded px-2.5 py-1.5 border border-ouro-border/30"
          >
            <span className="font-mono text-ouro-muted">{j.id.slice(0, 8)}</span>
            <span className="text-ouro-green uppercase text-[10px] tracking-wider">
              {j.status}
            </span>
            <span className="font-mono text-ouro-muted">${j.price_usdc.toFixed(4)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
