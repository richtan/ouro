import { NextRequest, NextResponse } from "next/server";

const IMAGE_RE = /^[a-zA-Z0-9][a-zA-Z0-9._/-]*$/;
const TIMEOUT_MS = 5_000;

export async function GET(req: NextRequest) {
  const image = req.nextUrl.searchParams.get("image")?.trim();
  if (!image || !IMAGE_RE.test(image)) {
    return NextResponse.json({ tags: [] }, { headers: cacheHeaders() });
  }

  const hasSlash = image.includes("/");
  const namespace = hasSlash ? image.split("/")[0] : "library";
  const repository = hasSlash ? image.split("/").slice(1).join("/") : image;

  const url = `https://hub.docker.com/v2/namespaces/${namespace}/repositories/${repository}/tags?page_size=25`;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);

    if (!res.ok) {
      return NextResponse.json({ tags: [] }, { headers: cacheHeaders() });
    }

    const data = await res.json();
    const tags: string[] = (data.results ?? []).map(
      (r: { name: string }) => r.name,
    );

    return NextResponse.json({ tags }, { headers: cacheHeaders() });
  } catch {
    return NextResponse.json({ tags: [] }, { headers: cacheHeaders() });
  }
}

function cacheHeaders() {
  return { "Cache-Control": "public, max-age=300, stale-while-revalidate=600" };
}
