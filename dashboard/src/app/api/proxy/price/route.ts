import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL not configured" }, { status: 502 });
  }

  const params = req.nextUrl.searchParams.toString();
  try {
    const res = await fetch(`${agentUrl}/api/price?${params}`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to fetch price" }, { status: 502 });
  }
}
