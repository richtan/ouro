import { NextRequest, NextResponse } from "next/server";
import { fetchWithTimeout } from "@/lib/api";

export const dynamic = "force-dynamic";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;

  if (!UUID_RE.test(jobId)) {
    return NextResponse.json(
      { error: "Invalid job ID format" },
      { status: 400 },
    );
  }

  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) {
    return NextResponse.json(
      { error: "AGENT_URL is not configured" },
      { status: 502 },
    );
  }

  try {
    const url = new URL(`${agentUrl}/api/jobs/${jobId}/events`);

    const headers: Record<string, string> = {
      Accept: "text/event-stream",
    };
    if (process.env.ADMIN_API_KEY) {
      headers["x-admin-key"] = process.env.ADMIN_API_KEY;
    }

    const upstream = await fetchWithTimeout(url.toString(), { headers }, 10_000);

    if (!upstream.ok) {
      return NextResponse.json(
        { error: "Agent job events returned non-OK status" },
        { status: 502 },
      );
    }

    if (upstream.body === null) {
      return NextResponse.json(
        { error: "Agent job events returned null body" },
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
      { error: "Failed to connect to agent job events stream" },
      { status: 502 },
    );
  }
}
