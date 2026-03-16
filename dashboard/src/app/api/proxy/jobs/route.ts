import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";
import { getWalletFromRequest } from "@/lib/wallet-auth";

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

    const wallet = await getWalletFromRequest();
    if (!wallet) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    // Verify the session wallet matches the requested address
    if (wallet.toLowerCase() !== address.toLowerCase()) {
      return NextResponse.json({ error: "Address mismatch" }, { status: 403 });
    }

    const headers: Record<string, string> = {};
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }
    const res = await fetchWithTimeout(
      `${agentUrl}/api/jobs/user?address=${encodeURIComponent(address)}`,
      { headers },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to fetch user jobs" }, { status: 502 });
  }
}
