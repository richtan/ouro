import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL not configured" }, { status: 502 });
  }

  const wallet = request.nextUrl.searchParams.get("wallet");
  const signature = request.nextUrl.searchParams.get("signature");
  const timestamp = request.nextUrl.searchParams.get("timestamp");

  if (!wallet || !/^0x[0-9a-fA-F]{40}$/.test(wallet)) {
    return NextResponse.json({ error: "Invalid wallet address" }, { status: 400 });
  }
  if (!signature || !timestamp) {
    return NextResponse.json({ error: "signature and timestamp required" }, { status: 401 });
  }

  try {
    const params = new URLSearchParams({ wallet, signature, timestamp });
    const res = await fetchWithTimeout(`${agentUrl}/api/storage?${params}`);
    const data = await res.text();
    return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return NextResponse.json({ error: "Failed to reach agent" }, { status: 502 });
  }
}
