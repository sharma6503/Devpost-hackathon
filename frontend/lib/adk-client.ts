import type { Session, ReviewState } from "@/types/adk";
import { getStoredAppName, getStoredAdkBaseUrl } from "@/lib/session";

const BASE = "/api/adk";
const DEFAULT_APP_NAME = process.env.NEXT_PUBLIC_ADK_APP_NAME ?? "agent_guardian";

function resolveAppName(appName?: string): string {
  if (appName && appName.trim()) return appName.trim();
  return getStoredAppName() || DEFAULT_APP_NAME;
}

function getHeaders(customBaseUrl?: string): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const base = customBaseUrl || getStoredAdkBaseUrl();
  if (base) {
    headers["x-adk-base-url"] = base;
  }
  return headers;
}

/**
 * Discovers available Google ADK apps running on the backend.
 * Queries /list-apps or /apps and returns registered application names.
 */
export async function listApps(customBaseUrl?: string): Promise<string[]> {
  const headers = getHeaders(customBaseUrl);
  try {
    const res = await fetch(`${BASE}/list-apps`, {
      headers,
      signal: AbortSignal.timeout(5_000),
    });
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) return data;
      if (Array.isArray(data?.apps) && data.apps.length > 0) return data.apps;
    }
  } catch {
    // Fall back to /apps endpoint if /list-apps is not configured
  }

  try {
    const res = await fetch(`${BASE}/apps`, {
      headers,
      signal: AbortSignal.timeout(5_000),
    });
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) return data;
      if (Array.isArray(data?.apps) && data.apps.length > 0) return data.apps;
    }
  } catch {
    // Backend unreachable or custom structure
  }

  const fallback = resolveAppName();
  return [fallback];
}

export async function createSession(
  userId: string,
  sessionId: string,
  initialState?: Partial<ReviewState>,
  appName?: string,
  customBaseUrl?: string
): Promise<Session> {
  const app = resolveAppName(appName);
  const res = await fetch(
    `${BASE}/apps/${app}/users/${userId}/sessions/${sessionId}`,
    {
      method: "POST",
      headers: getHeaders(customBaseUrl),
      body: JSON.stringify(initialState ?? {}),
    }
  );
  if (!res.ok) throw new Error(`Create session failed: ${res.status}`);
  return res.json();
}

export async function getSession(
  userId: string,
  sessionId: string,
  appName?: string,
  customBaseUrl?: string
): Promise<Session> {
  const app = resolveAppName(appName);
  const res = await fetch(
    `${BASE}/apps/${app}/users/${userId}/sessions/${sessionId}`,
    {
      headers: getHeaders(customBaseUrl),
    }
  );
  if (!res.ok) throw new Error(`Get session failed: ${res.status}`);
  return res.json();
}

/** Get an existing session or create it if not found. */
export async function getOrCreateSession(
  userId: string,
  sessionId: string,
  initialState?: Partial<ReviewState>,
  appName?: string,
  customBaseUrl?: string
): Promise<Session> {
  try {
    return await getSession(userId, sessionId, appName, customBaseUrl);
  } catch {
    return await createSession(userId, sessionId, initialState, appName, customBaseUrl);
  }
}

/** Delete a session from ADK's in-memory store. */
export async function deleteAdkSession(
  userId: string,
  sessionId: string,
  appName?: string,
  customBaseUrl?: string
): Promise<void> {
  const app = resolveAppName(appName);
  await fetch(
    `${BASE}/apps/${app}/users/${userId}/sessions/${sessionId}`,
    {
      method: "DELETE",
      headers: getHeaders(customBaseUrl),
    }
  ).catch(() => { /* ignore if ADK is offline */ });
}

/** List all sessions for a user from ADK's in-memory store. */
export async function listSessions(
  userId: string,
  appName?: string,
  customBaseUrl?: string
): Promise<Session[]> {
  const app = resolveAppName(appName);
  let res: Response;
  try {
    res = await fetch(
      `${BASE}/apps/${app}/users/${userId}/sessions`,
      {
        headers: getHeaders(customBaseUrl),
        signal: AbortSignal.timeout(15_000),
      }
    );
  } catch (err) {
    if (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError")) {
      return [];
    }
    throw err;
  }
  if (res.status === 504 || res.status === 502) {
    throw new Error(`ADK backend unreachable (${res.status})`);
  }
  if (!res.ok) return [];
  try {
    const data = await res.json();
    return Array.isArray(data) ? data : (data.sessions ?? []);
  } catch {
    return [];
  }
}

/** Returns true if the ADK backend is reachable right now. */
export async function checkHealth(customBaseUrl?: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/healthz`, {
      headers: getHeaders(customBaseUrl),
      signal: AbortSignal.timeout(5_000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export interface ArtifactPart {
  text?: string;
  inlineData?: { mimeType: string; data: string; displayName?: string };
}

/** List artifact filenames saved for a session (ADK artifact service). */
export async function listArtifacts(
  userId: string,
  sessionId: string,
  appName?: string,
  customBaseUrl?: string
): Promise<string[]> {
  const app = resolveAppName(appName);
  const res = await fetch(
    `${BASE}/apps/${app}/users/${userId}/sessions/${sessionId}/artifacts`,
    {
      headers: getHeaders(customBaseUrl),
    }
  );
  if (!res.ok) return [];
  try {
    const data = await res.json();
    return Array.isArray(data) ? data : (data.artifactNames ?? data.artifacts ?? []);
  } catch {
    return [];
  }
}

/** Load the latest version of a named artifact as a Part. */
export async function getArtifact(
  userId: string,
  sessionId: string,
  name: string,
  appName?: string,
  customBaseUrl?: string
): Promise<ArtifactPart | null> {
  const app = resolveAppName(appName);
  const res = await fetch(
    `${BASE}/apps/${app}/users/${userId}/sessions/${sessionId}/artifacts/${encodeURIComponent(name)}`,
    {
      headers: getHeaders(customBaseUrl),
    }
  );
  if (!res.ok) return null;
  try {
    const raw = await res.json();
    if (!raw || typeof raw !== "object") return null;
    const inline = raw.inlineData ?? raw.inline_data;
    return {
      text: raw.text,
      inlineData: inline
        ? {
            mimeType: inline.mimeType ?? inline.mime_type ?? "application/octet-stream",
            data: inline.data,
            displayName: inline.displayName ?? inline.display_name,
          }
        : undefined,
    };
  } catch {
    return null;
  }
}

export interface RunPayload {
  userId: string;
  sessionId: string;
  messageText: string;
  appName?: string;
  customBaseUrl?: string;
  inlineFiles?: Array<{
    displayName: string;
    data: string;
    mimeType: string;
  }>;
}

export function runSse(
  payload: RunPayload,
  signal?: AbortSignal
): ReadableStream<Uint8Array> {
  const { userId, sessionId, messageText, inlineFiles, appName, customBaseUrl } = payload;
  const targetApp = resolveAppName(appName);

  const parts: Array<Record<string, unknown>> = [{ text: messageText }];
  if (inlineFiles) {
    for (const f of inlineFiles) {
      parts.push({ inlineData: f });
    }
  }

  const body = JSON.stringify({
    appName: targetApp,
    userId,
    sessionId,
    newMessage: { role: "user", parts },
    streaming: true,
  });

  return new ReadableStream({
    async start(controller) {
      try {
        const res = await fetch(`${BASE}/run_sse`, {
          method: "POST",
          headers: getHeaders(customBaseUrl),
          body,
          signal,
        });
        if (!res.ok) {
          controller.error(new Error(`Run SSE failed: ${res.status}`));
          return;
        }
        const reader = res.body!.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }
        controller.close();
      } catch (err) {
        controller.error(err);
      }
    },
  });
}
