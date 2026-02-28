import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(
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
    const body = await request.text();
    const res = await fetch(`${agentUrl}/api/sessions/${sessionId}/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to complete session" }, { status: 502 });
  }
}
