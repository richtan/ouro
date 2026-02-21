import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json(
      { error: "AGENT_URL is not configured" },
      { status: 502 }
    );
  }

  try {
    const res = await fetch(`${agentUrl}/api/wallet`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to fetch wallet from agent" },
      { status: 502 }
    );
  }
}
