"use client";

import { useEffect, useRef, useState } from "react";

interface LogEntry {
  type: string;
  message: string;
  timestamp: string;
}

const TYPE_STYLES: Record<string, string> = {
  system: "text-blue-400",
  agent: "text-ouro-accent",
  slurm: "text-ouro-amber",
  chain: "text-ouro-green",
  cost: "text-purple-400",
  slurm_error: "text-ouro-red",
  chain_error: "text-ouro-red",
  error: "text-ouro-red",
  heartbeat: "text-ouro-muted",
};

export default function TerminalFeed() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource(`/api/stream`);

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setLogs((prev) => [...prev.slice(-200), data]);
      } catch {
        /* skip unparseable */
      }
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    if (!paused && feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [logs, paused]);

  return (
    <div className="card col-span-full animate-slide-up">
      <div className="flex items-center justify-between mb-4">
        <div className="stat-label">Agent Terminal</div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setPaused(!paused)}
            className="text-[10px] font-mono text-ouro-muted hover:text-ouro-text transition-colors uppercase tracking-wider"
          >
            {paused ? "▶ Resume" : "⏸ Pause"}
          </button>
          <div className="flex items-center gap-1.5">
            <div
              className={`w-2 h-2 rounded-full ${
                connected ? "bg-ouro-green animate-pulse" : "bg-ouro-red"
              }`}
            />
            <span className="text-[10px] font-mono text-ouro-muted uppercase tracking-wider">
              {connected ? "SSE Live" : "Disconnected"}
            </span>
          </div>
        </div>
      </div>
      <div
        ref={feedRef}
        className="h-64 overflow-y-auto bg-black/40 rounded-lg border border-ouro-border/30 p-3 font-mono text-xs space-y-0.5"
      >
        {logs.length === 0 && (
          <div className="text-ouro-muted py-6 text-center">Waiting for agent events...</div>
        )}
        {logs.map((log, i) => {
          const ts = new Date(log.timestamp).toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
          const color = TYPE_STYLES[log.type] ?? "text-ouro-text";
          return (
            <div key={i} className="flex gap-2 leading-relaxed">
              <span className="text-ouro-muted/60 shrink-0">{ts}</span>
              <span
                className={`shrink-0 w-14 text-right uppercase text-[10px] leading-[18px] ${color}`}
              >
                {log.type.replace("_", " ")}
              </span>
              <span className="text-ouro-text/80 break-all">{log.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
