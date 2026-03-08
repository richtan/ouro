import { useEffect, useRef, useState } from "react";

interface JobEvent {
  type: string;
  message: string;
  timestamp: string;
  job_id?: string;
}

/** Map jobStatus to timeline stage for fallback */
function statusToStage(status: string): number {
  switch (status) {
    case "pending":
      return 1;
    case "processing":
      return 1;
    case "running":
      return 3;
    case "completed":
    case "completed_no_proof":
    case "failed":
      return 5;
    default:
      return 0;
  }
}

/** Derive stage from the most advanced event type seen */
function eventsToStage(events: JobEvent[]): number {
  let stage = 0;
  for (const e of events) {
    if (e.type === "agent" && stage < 1) stage = 1;
    if (e.type === "slurm" && stage < 2) stage = 2;
    if (e.type === "slurm" && e.message.includes("state=RUNNING")) stage = 3;
    if (e.type === "slurm" && e.message.includes("completed")) stage = 3;
    if (e.type === "chain") stage = 4;
    if (e.type === "profit" || e.type === "job") stage = 5;
  }
  return stage;
}

const MAX_SSE_CONNECTIONS = 3;
let activeConnections = 0;

export function useJobEvents(jobId: string | null, jobStatus: string) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [sseStage, setSseStage] = useState<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const isTerminal = ["completed", "completed_no_proof", "failed"].includes(
    jobStatus,
  );
  const currentStage = sseStage ?? statusToStage(jobStatus);

  useEffect(() => {
    if (!jobId) {
      setEvents([]);
      setSseStage(null);
      return;
    }
    if (isTerminal) {
      // Job finished — close SSE if open, but preserve events in state
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        activeConnections--;
      }
      return;
    }
    if (activeConnections >= MAX_SSE_CONNECTIONS) return;

    activeConnections++;
    const es = new EventSource(`/api/proxy/jobs/${jobId}/events`);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: JobEvent = JSON.parse(e.data);
        setEvents((prev) => {
          const next = [...prev, event];
          setSseStage(eventsToStage(next));
          return next;
        });
      } catch {
        /* skip unparseable */
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; no action needed
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
      activeConnections--;
      // DO NOT clear events — only the !jobId branch above clears state
    };
  }, [jobId, isTerminal]);

  return { events, currentStage };
}
