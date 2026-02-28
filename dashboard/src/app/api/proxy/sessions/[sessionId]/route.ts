import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL is not configured" }, { status: 502 });
  }

  const { sessionId } = await params;
  if (!sessionId) {
    return NextResponse.json({ error: "sessionId required" }, { status: 400 });
  }

  try {
    const res = await fetch(`${agentUrl}/api/sessions/${sessionId}`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to fetch session" }, { status: 502 });
  }
}
