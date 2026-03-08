"use client";

import { useEffect, useRef } from "react";

interface JobEvent {
  type: string;
  message: string;
  timestamp: string;
}

const TYPE_COLORS: Record<string, string> = {
  system: "text-o-blueText",
  agent: "text-o-blueText",
  slurm: "text-o-amber",
  chain: "text-o-green",
  cost: "text-o-text",
  slurm_error: "text-o-red",
  chain_error: "text-o-red",
  error: "text-o-red",
  heartbeat: "text-o-muted",
  scaler: "text-o-amber",
  profit: "text-o-green",
  job: "text-o-blueText",
  agent_error: "text-o-red",
  x402: "text-o-green",
};

export default function JobEventFeed({ events }: { events: JobEvent[] }) {
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events]);

  return (
    <div>
      <div
        ref={feedRef}
        className="max-h-32 overflow-y-auto bg-o-bg rounded-lg border border-o-border p-2 font-mono text-xs"
      >
        {events.length === 0 ? (
          <div className="text-o-muted">Waiting for events...</div>
        ) : (
          events.map((event, i) => {
            const color = TYPE_COLORS[event.type] ?? "text-o-textSecondary";
            const isError =
              event.type === "error" ||
              event.type === "slurm_error" ||
              event.type === "chain_error" ||
              event.type === "agent_error";
            return (
              <div key={i} className="py-0.5">
                <span className="text-o-muted">
                  {new Date(event.timestamp).toLocaleTimeString("en-US", {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>{" "}
                <span
                  className={`uppercase tracking-wider ${isError ? "text-o-red" : color}`}
                >
                  [{event.type.replace("_", " ")}]
                </span>{" "}
                <span className={isError ? "text-o-red" : "text-o-text/80"}>
                  {event.message}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
