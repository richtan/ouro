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
    const { searchParams } = new URL(request.url);
    const url = new URL(`${agentUrl}/api/stream`);
    searchParams.forEach((value, key) => {
      url.searchParams.append(key, value);
    });

    const upstream = await fetch(url.toString(), {
      headers: {
        Accept: "text/event-stream",
        ...Object.fromEntries(request.headers.entries()),
      },
    });

    if (!upstream.ok) {
      return NextResponse.json(
        { error: "Agent stream returned non-OK status" },
        { status: 502 }
      );
    }

    if (upstream.body === null) {
      return NextResponse.json(
        { error: "Agent stream returned null body" },
        { status: 502 }
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
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to connect to agent stream" },
      { status: 502 }
    );
  }
}
