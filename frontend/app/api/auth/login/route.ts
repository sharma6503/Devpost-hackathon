import { type NextRequest, NextResponse } from "next/server";

// Mirrors the base-URL resolution in ../../adk/[...path]/route.ts, kept
// separate here because this route has different concerns (no allowlist, no
// streaming). 30s (not the 120s CRUD budget) — but long enough to cover a
// cold-start BigQuery client (ADC token fetch + first query) on the backend's
// first login attempt after a restart.
const ADK_BASE_CONFIGURED = process.env.ADK_BASE_URL ?? process.env.NEXT_PUBLIC_ADK_BASE_URL ?? null;
const DEV_FALLBACK = "http://127.0.0.1:8000";

function resolveAdkBase(): string {
  return ADK_BASE_CONFIGURED || DEV_FALLBACK;
}

export async function POST(req: NextRequest) {
  const adkBase = resolveAdkBase();


  const body = await req.text();
  let upstream: Response;
  try {
    upstream = await fetch(`${adkBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return NextResponse.json({ error: "Auth backend unreachable" }, { status: 504 });
  }

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
