import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_COOKIE_NAME,
  isAdminAuthEnabled,
  verifyAdminJWT,
} from "@/lib/admin-auth";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

const ALLOWED_EVENT_TYPES = new Set([
  "payment_received",
  "job_completed",
  "job_failed",
  "credit_issued",
  "credit_redeemed",
  "gas_cost",
  "llm_cost",
  "heartbeat",
  "pricing_update",
  "error",
]);

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

    if (limit) {
      const parsed = parseInt(limit, 10);
      if (isNaN(parsed) || parsed < 1 || parsed > 1000) {
        return NextResponse.json(
          { error: "limit must be a number between 1 and 1000" },
          { status: 400 },
        );
      }
      url.searchParams.set("limit", String(parsed));
    }
    if (eventType) {
      if (!ALLOWED_EVENT_TYPES.has(eventType)) {
        return NextResponse.json(
          { error: `Invalid event_type. Allowed: ${[...ALLOWED_EVENT_TYPES].join(", ")}` },
          { status: 400 },
        );
      }
      url.searchParams.set("event_type", eventType);
    }

    const headers: Record<string, string> = {};
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }

    const res = await fetchWithTimeout(url.toString(), { headers });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch audit log" },
      { status: 502 },
    );
  }
}
