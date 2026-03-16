import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function DELETE(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL not configured" }, { status: 502 });
  }

  const wallet = request.nextUrl.searchParams.get("wallet");
  const path = request.nextUrl.searchParams.get("path");
  const signature = request.nextUrl.searchParams.get("signature");
  const timestamp = request.nextUrl.searchParams.get("timestamp");
  if (!wallet || !/^0x[0-9a-fA-F]{40}$/.test(wallet)) {
    return NextResponse.json({ error: "Invalid wallet address" }, { status: 400 });
  }
  if (!path) {
    return NextResponse.json({ error: "path parameter required" }, { status: 400 });
  }
  if (!signature || !timestamp) {
    return NextResponse.json({ error: "signature and timestamp required" }, { status: 401 });
  }

  try {
    const qs = new URLSearchParams({ wallet, path, signature, timestamp });
    const res = await fetchWithTimeout(
      `${agentUrl}/api/storage/files?${qs}`,
      { method: "DELETE" },
    );
    const data = await res.text();
    return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return NextResponse.json({ error: "Failed to reach agent" }, { status: 502 });
  }
}
