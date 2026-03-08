import { useEffect, useRef, useState } from "react";

export interface JobEvent {
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
    case "failed":
      return 4;
    default:
      return 0;
  }
}

interface StageInfo {
  stage: number;
  sseFailed: boolean;
  sseFailedStage: number;
}

/** Derive stage from the most advanced event type seen, detecting SSE failures */
function eventsToStageInfo(events: JobEvent[]): StageInfo {
  let stage = 0;
  let sseFailed = false;
  let sseFailedStage = 0;
  for (const e of events) {
    if (e.type === "agent" && stage < 1) stage = 1;
    if (e.type === "slurm" && stage < 2) stage = 2;
    if (e.type === "slurm" && e.message.includes("state=RUNNING")) stage = 3;
    if (e.type === "slurm" && e.message.includes("completed")) stage = 3;
    if (e.type === "profit" || e.type === "job") {
      // Detect failure: " failed (" matches "Job x failed (user_error): ..."
      // but NOT "retrying (1/2): Slurm submit failed: ..." (different position)
      if (e.type === "job" && e.message.includes(" failed (")) {
        sseFailed = true;
        sseFailedStage = stage;
      }
      stage = 4;
    }
  }
  return { stage, sseFailed, sseFailedStage };
}

const MAX_SSE_CONNECTIONS = 3;
let activeConnections = 0;

export function useJobEvents(jobId: string | null, jobStatus: string, persistedEvents?: JobEvent[]) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [sseStage, setSseStage] = useState<number | null>(null);
  const [sseFailed, setSseFailed] = useState(false);
  const [sseFailedStage, setSseFailedStage] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const loadedPersistedRef = useRef(false);

  const isTerminal = ["completed", "failed"].includes(jobStatus);
  const currentStage = sseStage ?? statusToStage(jobStatus);

  // Load persisted events for terminal jobs that have no SSE events
  useEffect(() => {
    if (isTerminal && persistedEvents && persistedEvents.length > 0 && !loadedPersistedRef.current) {
      loadedPersistedRef.current = true;
      setEvents(persistedEvents);
      const info = eventsToStageInfo(persistedEvents);
      setSseStage(info.stage);
      setSseFailed(info.sseFailed);
      setSseFailedStage(info.sseFailedStage);
    }
  }, [isTerminal, persistedEvents]);

  useEffect(() => {
    if (!jobId) {
      setEvents([]);
      setSseStage(null);
      setSseFailed(false);
      setSseFailedStage(0);
      loadedPersistedRef.current = false;
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
          const info = eventsToStageInfo(next);
          setSseStage(info.stage);
          setSseFailed(info.sseFailed);
          setSseFailedStage(info.sseFailedStage);
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

  return { events, currentStage, sseFailed, sseFailedStage };
}
