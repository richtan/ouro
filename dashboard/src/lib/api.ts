const BASE = "";

async function jsonOrThrow(res: Response) {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/stats`, { cache: "no-store" });
  return jsonOrThrow(res);
}

export async function fetchWallet() {
  const res = await fetch(`${BASE}/api/wallet`, { cache: "no-store" });
  return jsonOrThrow(res);
}

export async function fetchJobs() {
  const res = await fetch(`${BASE}/api/jobs`, { cache: "no-store" });
  return jsonOrThrow(res);
}

export async function fetchAttribution() {
  const res = await fetch(`${BASE}/api/attribution`, { cache: "no-store" });
  return jsonOrThrow(res);
}

export async function decodeBuilderCodes(calldata: string) {
  const res = await fetch(
    `${BASE}/api/attribution/decode?calldata=${encodeURIComponent(calldata)}`,
    { cache: "no-store" }
  );
  return jsonOrThrow(res);
}

export async function fetchAudit(limit?: number, eventType?: string) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (eventType) params.set("event_type", eventType);
  const qs = params.toString();
  const res = await fetch(`${BASE}/api/audit${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
  return jsonOrThrow(res);
}
