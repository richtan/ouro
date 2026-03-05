import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL is not configured" }, { status: 502 });
  }

  const { sessionId } = await params;
  if (!sessionId || !UUID_RE.test(sessionId)) {
    return NextResponse.json({ error: "Invalid sessionId format (expected UUID)" }, { status: 400 });
  }

  try {
    const res = await fetchWithTimeout(`${agentUrl}/api/sessions/${sessionId}`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to fetch session" }, { status: 502 });
  }
}
