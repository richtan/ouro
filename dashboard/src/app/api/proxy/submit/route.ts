import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json({ error: "AGENT_URL is not configured" }, { status: 502 });
  }

  try {
    const body = await request.text();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const paymentSig = request.headers.get("payment-signature");
    if (paymentSig) headers["payment-signature"] = paymentSig;
    const builderCode = request.headers.get("X-BUILDER-CODE");
    if (builderCode) headers["X-BUILDER-CODE"] = builderCode;

    const upstream = await fetchWithTimeout(`${agentUrl}/api/compute/submit`, {
      method: "POST",
      headers,
      body,
    });

    const responseHeaders = new Headers();
    const paymentRequired = upstream.headers.get("PAYMENT-REQUIRED");
    if (paymentRequired) {
      responseHeaders.set("PAYMENT-REQUIRED", paymentRequired);
    }

    const data = await upstream.text();
    return new NextResponse(data, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json({ error: "Failed to reach agent" }, { status: 502 });
  }
}
