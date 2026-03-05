import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

const TX_HASH_RE = /^0x[0-9a-fA-F]{64}$/;

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
    if (!TX_HASH_RE.test(txHash)) {
      return NextResponse.json(
        { error: "Invalid tx_hash format (expected 0x + 64 hex chars)" },
        { status: 400 }
      );
    }
    const url = new URL(`${agentUrl}/api/attribution/decode`);
    url.searchParams.set("tx_hash", txHash);
    const res = await fetchWithTimeout(url.toString());
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to decode attribution from agent" },
      { status: 502 }
    );
  }
}
