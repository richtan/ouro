import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL not configured" }, { status: 502 });
  }

  const wallet = request.nextUrl.searchParams.get("wallet");
  if (!wallet || !/^0x[0-9a-fA-F]{40}$/.test(wallet)) {
    return NextResponse.json({ error: "Invalid wallet address" }, { status: 400 });
  }

  try {
    const res = await fetchWithTimeout(`${agentUrl}/api/storage?wallet=${wallet}`);
    const data = await res.text();
    return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return NextResponse.json({ error: "Failed to reach agent" }, { status: 502 });
  }
}
