import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";
import { getWalletFromRequest } from "@/lib/wallet-auth";

export const dynamic = "force-dynamic";

export async function DELETE(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL not configured" }, { status: 502 });
  }

  const walletParam = request.nextUrl.searchParams.get("wallet");
  const path = request.nextUrl.searchParams.get("path");
  if (!walletParam || !/^0x[0-9a-fA-F]{40}$/.test(walletParam)) {
    return NextResponse.json({ error: "Invalid wallet address" }, { status: 400 });
  }
  if (!path) {
    return NextResponse.json({ error: "path parameter required" }, { status: 400 });
  }

  const sessionWallet = await getWalletFromRequest();
  if (!sessionWallet) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  }

  if (sessionWallet.toLowerCase() !== walletParam.toLowerCase()) {
    return NextResponse.json({ error: "Address mismatch" }, { status: 403 });
  }

  try {
    const headers: Record<string, string> = {};
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }
    const qs = new URLSearchParams({ wallet: walletParam, path });
    const res = await fetchWithTimeout(
      `${agentUrl}/api/storage/files?${qs}`,
      { method: "DELETE", headers },
    );
    const data = await res.text();
    return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return NextResponse.json({ error: "Failed to reach agent" }, { status: 502 });
  }
}
