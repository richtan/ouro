import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_COOKIE_NAME,
  isAdminAuthEnabled,
  verifyAdminJWT,
} from "@/lib/admin-auth";
import { fetchWithTimeout } from "@/lib/api";

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
    const url = new URL(`${agentUrl}/api/stream`);

    const headers: Record<string, string> = {
      Accept: "text/event-stream",
    };
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }

    // SSE connections are long-lived; use a longer timeout for initial connect only
    const upstream = await fetchWithTimeout(url.toString(), { headers }, 10_000);

    if (!upstream.ok) {
      return NextResponse.json(
        { error: "Agent stream returned non-OK status" },
        { status: 502 },
      );
    }

    if (upstream.body === null) {
      return NextResponse.json(
        { error: "Agent stream returned null body" },
        { status: 502 },
      );
    }

    const stream = new ReadableStream({
      async start(controller) {
        const reader = upstream.body!.getReader();
        try {
          let done = false;
          while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
              controller.enqueue(value);
            }
          }
          controller.close();
        } catch (err) {
          controller.error(err);
        } finally {
          reader.releaseLock();
        }
      },
    });

    return new NextResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to connect to agent stream" },
      { status: 502 },
    );
  }
}
