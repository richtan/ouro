const BASE = "";

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/stats`, { cache: "no-store" });
  return res.json();
}

export async function fetchWallet() {
  const res = await fetch(`${BASE}/api/wallet`, { cache: "no-store" });
  return res.json();
}

export async function fetchJobs() {
  const res = await fetch(`${BASE}/api/jobs`, { cache: "no-store" });
  return res.json();
}

export async function fetchAttribution() {
  const res = await fetch(`${BASE}/api/attribution`, { cache: "no-store" });
  return res.json();
}

export async function decodeBuilderCodes(calldata: string) {
  const res = await fetch(
    `${BASE}/api/attribution/decode?calldata=${encodeURIComponent(calldata)}`,
    { cache: "no-store" }
  );
  return res.json();
}
