"use client";

import { useEffect, useRef, useState } from "react";

interface LogEntry {
  type: string;
  message: string;
  timestamp: string;
}

const TYPE_COLORS: Record<string, string> = {
  system: "text-o-blueText",
  agent: "text-o-blueText",
  slurm: "text-o-amber",
  cost: "text-o-text",
  slurm_error: "text-o-red",
  error: "text-o-red",
  heartbeat: "text-o-muted",
};

export default function TerminalFeed() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource("/api/stream");

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
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="stat-label">Agent Terminal</div>
          <div className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${connected ? "bg-o-green animate-pulse" : "bg-o-red"}`} />
            <span className="text-xs text-o-muted">{connected ? "Live" : "Offline"}</span>
          </div>
        </div>
        <button
          onClick={() => setPaused(!paused)}
          className="px-3 py-2 text-xs rounded-lg border border-o-border hover:border-o-borderHover transition-colors text-o-textSecondary hover:text-o-text"
        >
          {paused ? "Resume" : "Pause"}
        </button>
      </div>

      <div
        ref={feedRef}
        className="h-48 sm:h-64 overflow-y-auto bg-o-bg rounded-lg border border-o-border p-3 font-mono text-xs leading-relaxed"
      >
        {logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-o-muted">
            Waiting for agent activity...
          </div>
        ) : (
          logs.map((log, i) => {
            const color = TYPE_COLORS[log.type] ?? "text-o-textSecondary";
            const isError =
              log.type === "error" ||
              log.type === "slurm_error" ||
              log.message.toLowerCase().includes("error");
            return (
              <div key={i} className={`py-0.5 ${isError ? "text-o-red" : ""}`}>
                <span className="text-o-muted">
                  {new Date(log.timestamp).toLocaleTimeString("en-US", {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                {" "}
                <span className={`uppercase tracking-wider ${isError ? "text-o-red" : color}`}>
                  [{log.type.replace("_", " ")}]
                </span>
                {" "}
                <span className={isError ? "text-o-red" : "text-o-text/80"}>
                  {log.message}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
