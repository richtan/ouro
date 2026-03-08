import { NextRequest, NextResponse } from "next/server";

const IMAGE_RE = /^[a-zA-Z0-9][a-zA-Z0-9._/-]*$/;
const PER_PAGE_TIMEOUT_MS = 5_000;
const OVERALL_TIMEOUT_MS = 10_000;
const MAX_PAGES = 3;
const PAGE_SIZE = 100;

const CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes
const NEGATIVE_CACHE_TTL_MS = 60 * 1000; // 1 minute for errors/empty
const MAX_CACHE_SIZE = 200;

interface CacheEntry {
  tags: string[];
  ts: number;
  ttl: number;
}

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<string[]>>();

/** Extract leading semver-like prefix: "3.13-slim" → [3, 13] */
function versionKey(tag: string): number[] | null {
  const m = tag.match(/^(\d+(?:\.\d+)*)/);
  if (!m) return null;
  return m[1].split(".").map(Number);
}

/** Sort tags by version descending; non-versioned tags go to the end alphabetically */
function sortTagsByVersion(tags: string[]): string[] {
  return tags.sort((a, b) => {
    const va = versionKey(a);
    const vb = versionKey(b);

    // Both have no version → alphabetical
    if (!va && !vb) return a.localeCompare(b);
    // Only one has version → versioned first
    if (!va) return 1;
    if (!vb) return -1;

    // Compare version segments descending
    const len = Math.max(va.length, vb.length);
    for (let i = 0; i < len; i++) {
      const sa = va[i] ?? 0;
      const sb = vb[i] ?? 0;
      if (sa !== sb) return sb - sa; // descending
    }

    // Same version prefix → shorter tag first (e.g., "3.13" before "3.13-slim")
    return a.length - b.length;
  });
}

/** Evict oldest cache entry if over limit */
function evictIfNeeded() {
  if (cache.size <= MAX_CACHE_SIZE) return;
  let oldestKey: string | null = null;
  let oldestTs = Infinity;
  for (const [key, entry] of cache) {
    if (entry.ts < oldestTs) {
      oldestTs = entry.ts;
      oldestKey = key;
    }
  }
  if (oldestKey) cache.delete(oldestKey);
}

async function fetchTags(namespace: string, repository: string): Promise<string[]> {
  const tagSet = new Set<string>();
  const overallStart = Date.now();

  let nextUrl =
    `https://hub.docker.com/v2/namespaces/${namespace}/repositories/${repository}/tags?page_size=${PAGE_SIZE}` as string | null;

  for (let page = 0; page < MAX_PAGES && nextUrl; page++) {
    const remaining = OVERALL_TIMEOUT_MS - (Date.now() - overallStart);
    if (remaining <= 0) break;

    const timeout = Math.min(PER_PAGE_TIMEOUT_MS, remaining);
    const fetchUrl = nextUrl;

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      const res = await fetch(fetchUrl, { signal: controller.signal });
      clearTimeout(timer);

      if (!res.ok) break;

      const data: { results?: { name: string }[]; next?: string | null } = await res.json();
      for (const r of data.results ?? []) {
        tagSet.add(r.name);
      }

      nextUrl = data.next ?? null;
    } catch {
      // Timeout or network error — return what we have
      break;
    }
  }

  return sortTagsByVersion([...tagSet]);
}

export async function GET(req: NextRequest) {
  const image = req.nextUrl.searchParams.get("image")?.trim();
  if (!image || !IMAGE_RE.test(image)) {
    return NextResponse.json({ tags: [] }, { headers: cacheHeaders() });
  }

  const hasSlash = image.includes("/");
  const namespace = hasSlash ? image.split("/")[0] : "library";
  const repository = hasSlash ? image.split("/").slice(1).join("/") : image;
  const cacheKey = `${namespace}/${repository}`;

  // Check cache
  const cached = cache.get(cacheKey);
  if (cached && Date.now() - cached.ts < cached.ttl) {
    return NextResponse.json({ tags: cached.tags }, { headers: cacheHeaders() });
  }

  // Deduplicate in-flight requests
  let promise = inflight.get(cacheKey);
  if (!promise) {
    promise = fetchTags(namespace, repository).finally(() => {
      inflight.delete(cacheKey);
    });
    inflight.set(cacheKey, promise);
  }

  try {
    const tags = await promise;
    const ttl = tags.length === 0 ? NEGATIVE_CACHE_TTL_MS : CACHE_TTL_MS;
    cache.set(cacheKey, { tags, ts: Date.now(), ttl });
    evictIfNeeded();
    return NextResponse.json({ tags }, { headers: cacheHeaders() });
  } catch {
    cache.set(cacheKey, { tags: [], ts: Date.now(), ttl: NEGATIVE_CACHE_TTL_MS });
    evictIfNeeded();
    return NextResponse.json({ tags: [] }, { headers: cacheHeaders() });
  }
}

function cacheHeaders() {
  return { "Cache-Control": "public, max-age=300, stale-while-revalidate=600" };
}
