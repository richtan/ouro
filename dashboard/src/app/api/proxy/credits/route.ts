import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";
import { verifyMessage } from "viem";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL is not configured" }, { status: 502 });
  }

  try {
    const address = request.nextUrl.searchParams.get("address");
    if (!address) {
      return NextResponse.json({ error: "address parameter required" }, { status: 400 });
    }

    const signature = request.nextUrl.searchParams.get("signature");
    const timestamp = request.nextUrl.searchParams.get("timestamp");

    if (!signature || !timestamp) {
      return NextResponse.json({ error: "signature and timestamp required" }, { status: 401 });
    }

    const ts = parseInt(timestamp, 10);
    if (isNaN(ts) || Math.abs(Math.floor(Date.now() / 1000) - ts) > 300) {
      return NextResponse.json({ error: "Signature expired" }, { status: 401 });
    }

    const message = `ouro-list-my-data:${address.toLowerCase()}:${timestamp}`;
    try {
      const valid = await verifyMessage({
        address: address as `0x${string}`,
        message,
        signature: signature as `0x${string}`,
      });
      if (!valid) {
        return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
      }
    } catch {
      return NextResponse.json({ error: "Signature verification failed" }, { status: 401 });
    }

    const headers: Record<string, string> = {};
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }
    const res = await fetchWithTimeout(
      `${agentUrl}/api/credits/user?address=${encodeURIComponent(address)}`,
      { headers },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to fetch user credits" }, { status: 502 });
  }
}
