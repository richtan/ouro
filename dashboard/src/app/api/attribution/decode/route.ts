import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json(
      { error: "AGENT_URL is not configured" },
      { status: 502 }
    );
  }

  try {
    const txHash = request.nextUrl.searchParams.get("tx_hash");
    if (!txHash) {
      return NextResponse.json(
        { error: "tx_hash parameter required" },
        { status: 400 }
      );
    }
    const url = new URL(`${agentUrl}/api/attribution/decode`);
    url.searchParams.set("tx_hash", txHash);
    const res = await fetch(url.toString());
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to decode attribution from agent" },
      { status: 502 }
    );
  }
}
