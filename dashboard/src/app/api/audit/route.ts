import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_COOKIE_NAME,
  isAdminAuthEnabled,
  verifyAdminJWT,
} from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json(
      { error: "AGENT_URL is not configured" },
      { status: 502 },
    );
  }

  if (isAdminAuthEnabled()) {
    const cookieStore = await cookies();
    const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value;
    if (!token || !(await verifyAdminJWT(token))) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
  }

  try {
    const url = new URL(`${agentUrl}/api/audit`);
    const limit = request.nextUrl.searchParams.get("limit");
    const eventType = request.nextUrl.searchParams.get("event_type");
    if (limit) url.searchParams.set("limit", limit);
    if (eventType) url.searchParams.set("event_type", eventType);

    const headers: Record<string, string> = {};
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }

    const res = await fetch(url.toString(), { headers });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch audit log" },
      { status: 502 },
    );
  }
}
