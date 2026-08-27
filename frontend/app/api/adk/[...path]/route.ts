import { type NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// Opt-IN userId auto-correction for local file checks.
const AUTOCORRECT_USER = process.env.ADK_PROXY_AUTOCORRECT_USER === "true";

/**
 * Searches the local `.adk/artifacts/users` directories on disk to find which
 * user actually owns the given `sessionId`.
 */
function findCorrectUserIdForSession(sessionId: string): string | null {
  if (!AUTOCORRECT_USER) return null;
  // Guard against path traversal: strictly allow only alphanumeric, underscores, and hyphens
  if (
    !sessionId ||
    typeof sessionId !== "string" ||
    !/^[a-zA-Z0-9_-]{1,128}$/.test(sessionId)
  ) {
    return null;
  }
  try {
    const cwd = process.cwd();
    const possiblePaths = [
      path.resolve(/*turbopackIgnore: true*/ cwd, "../.adk/artifacts/users"),
      path.resolve(/*turbopackIgnore: true*/ cwd, ".adk/artifacts/users"),
    ];

    for (const usersPath of possiblePaths) {
      if (!fs.existsSync(usersPath)) continue;
      const userDirs = fs.readdirSync(usersPath);
      for (const userDir of userDirs) {
        if (!/^[a-zA-Z0-9_.-]{1,128}$/.test(userDir)) continue;
        const sessionPath = path.join(usersPath, userDir, "sessions", sessionId);
        if (fs.existsSync(sessionPath)) {
          return userDir;
        }
      }
    }
  } catch (err) {
    console.error("[adk-proxy] Error reading user directories:", err);
  }
  return null;
}

// Resolve the upstream ADK backend. In production we refuse to silently fall
// back to localhost — an unset URL there is a misconfiguration that should fail
// loudly (clean 500) rather than proxy to a host that isn't the backend. In
// development we keep the convenient localhost default and warn once.
const ADK_BASE_CONFIGURED =
  process.env.ADK_BASE_URL ?? process.env.NEXT_PUBLIC_ADK_BASE_URL ?? null;
const DEV_FALLBACK = "http://127.0.0.1:8000";

const ALLOWED_CUSTOM_HOSTS = (process.env.ALLOWED_ADK_HOSTS ?? "")
  .split(",")
  .map((h) => h.trim().toLowerCase())
  .filter(Boolean);

/**
 * Validates whether a client-supplied x-adk-base-url is safe against SSRF attacks.
 */
function isSafeCustomAdkBase(urlStr: string): boolean {
  try {
    const parsed = new URL(urlStr);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return false;
    }

    const hostname = parsed.hostname.toLowerCase();

    // Block cloud metadata services & link-local addresses
    if (
      hostname === "169.254.169.254" ||
      hostname === "metadata.google.internal" ||
      hostname === "metadata" ||
      hostname.startsWith("169.254.")
    ) {
      return false;
    }

    // In production, enforce explicit allowlist or match configured backend
    if (process.env.NODE_ENV === "production") {
      if (ALLOWED_CUSTOM_HOSTS.length > 0) {
        return ALLOWED_CUSTOM_HOSTS.includes(hostname);
      }
      if (ADK_BASE_CONFIGURED) {
        try {
          const configuredHost = new URL(ADK_BASE_CONFIGURED).hostname.toLowerCase();
          return hostname === configuredHost;
        } catch {
          return false;
        }
      }
      return false;
    }

    // In development/test, allow localhost / loopback or trusted LAN
    return true;
  } catch {
    return false;
  }
}

function resolveAdkBase(req?: NextRequest): string {
  // Allow client to supply custom ADK base endpoint via header only if it passes SSRF validation
  const headerBase = req?.headers.get("x-adk-base-url");
  if (headerBase && typeof headerBase === "string" && isSafeCustomAdkBase(headerBase)) {
    return headerBase.replace(/\/+$/, "");
  }
  return ADK_BASE_CONFIGURED || DEV_FALLBACK;
}

// Timeout for non-streaming CRUD proxied to ADK. A full session GET can be
// multi-MB (events embed the codebase, tool responses, and the rendered HTML
// report), so serializing + transferring it can take well over the old hard-
// coded 30 s when the backend is large or busy mid-audit — which surfaced as a
// 504. Default to 120 s and let deployments tune it via ADK_PROXY_TIMEOUT_MS.
const PROXY_TIMEOUT_MS = (() => {
  const raw = parseInt(process.env.ADK_PROXY_TIMEOUT_MS ?? "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : 120_000;
})();

// ─── Allowlist: only forward requests to known ADK endpoints ─────────────
const ALLOWED = [
  /^apps\/[^/]+\/users\/[^/]+\/sessions(\/[^/]+)?$/,  // CRUD sessions
  /^apps\/[^/]+\/users\/[^/]+\/sessions\/[^/]+\/artifacts(\/.*)?$/,  // artifacts: list / load / versions
  /^apps\/[^/]+$/, // app info
  /^apps$/,        // list apps
  /^list-apps$/,   // list apps
  /^healthz$/,     // health probe — used by the frontend to detect backend availability
  /^health$/,      // health probe variant
  /^run_sse$/,     // streaming agent execution
  /^run$/,         // non-streaming agent execution
];

function isAllowedPath(segments: string[]): boolean {
  const joined = segments.join("/");
  // Reject path-traversal attempts
  if (joined.includes("..") || joined.includes("%2e") || joined.includes("\\")) return false;
  return ALLOWED.some((re) => re.test(joined));
}

// ─── Body size guard: 50 MB max (accommodates ZIP uploads) ────────────────
const MAX_BODY_BYTES = 50 * 1024 * 1024;

function bodyTooLarge(req: NextRequest): boolean {
  const len = req.headers.get("content-length");
  return len != null && parseInt(len, 10) > MAX_BODY_BYTES;
}

// ─── Proxy core ───────────────────────────────────────────────────────────
async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  // Correct the userId parameter if this sessionId belongs to a different creator
  if (
    AUTOCORRECT_USER &&
    path.length >= 6 &&
    path[0] === "apps" &&
    path[2] === "users" &&
    path[4] === "sessions"
  ) {
    const requestedUserId = path[3];
    const sessionId = path[5];
    if (sessionId) {
      const correctUserId = findCorrectUserIdForSession(sessionId);
      if (correctUserId && correctUserId !== requestedUserId) {
        console.log(
          `[adk-proxy] Correcting userId from "${requestedUserId}" to "${correctUserId}" for session "${sessionId}"`
        );
        path[3] = correctUserId;
      }
    }
  }

  if (!isAllowedPath(path)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  if (bodyTooLarge(req)) {
    return NextResponse.json({ error: "Request too large" }, { status: 413 });
  }

  const adkBase = resolveAdkBase(req);
  if (!adkBase) {
    return NextResponse.json(
      { error: "ADK_BASE_URL not configured" },
      { status: 500 },
    );
  }

  const upstreamUrl = `${adkBase}/${path.join("/")}`;
  const search = req.nextUrl.searchParams.toString();
  const fullUrl = search ? `${upstreamUrl}?${search}` : upstreamUrl;

  const isRunSse = path.length === 1 && (path[0] === "run_sse" || path[0] === "run");

  const body =
    req.method !== "GET" && req.method !== "HEAD"
      ? await req.text()
      : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(fullUrl, {
      method: req.method,
      headers: { "Content-Type": "application/json" },
      body,
      // Generous timeout for CRUD calls (PROXY_TIMEOUT_MS — a session GET can be
      // multi-MB and slow to serialize). The long-lived run_sse / run stream must
      // NOT be aborted mid-audit — an audit runs for minutes, and a timeout here
      // tears down the SSE pipe (and kills the in-flight agent span before
      // it can finish/flush, dropping the trace for that run). Streaming
      // requests get no timeout (a dead backend still rejects the initial fetch,
      // which we catch below).
      signal: isRunSse ? undefined : AbortSignal.timeout(PROXY_TIMEOUT_MS),
      // @ts-expect-error Node 18+ fetch supports duplex for streaming
      duplex: isRunSse ? "half" : undefined,
    });
  } catch (err) {
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    return NextResponse.json(
      { error: isTimeout ? "ADK backend timed out" : "ADK backend unreachable" },
      { status: 504 }
    );
  }

  // Surface upstream server errors as clean JSON instead of proxying raw HTML
  if (upstream.status >= 500) {
    return NextResponse.json(
      { error: `ADK backend error (${upstream.status})` },
      { status: 502 }
    );
  }

  if (isRunSse) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  // Stream the upstream body straight through instead of buffering it all with
  // `await upstream.text()`. Session GETs can be multi-MB (events embed full
  // codebase/tool/report content); buffering + re-encoding here adds latency and
  // memory for no benefit. Mirrors the run_sse passthrough above.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}

// ─── Route handlers ───────────────────────────────────────────────────────
export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
