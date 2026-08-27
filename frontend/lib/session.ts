import type { LogEntry, PipelinePhase } from "@/types/adk";

const SESSION_STORAGE_KEY = "ag_sessions";
const SESSION_CACHE_PREFIX = "ag_sc_";
const PAYLOAD_CACHE_PREFIX = "ag_payload_";
const MAX_CACHE_BYTES = 2_000_000;

export function generateSessionId(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 20);
}

export function generateUserId(): string {
  if (typeof window === "undefined") return "web_user";
  const stored = localStorage.getItem("ag_user_id");
  if (stored) return stored;
  // Use a stable UUID tied to this browser so ADK sessions are consistent
  const id = crypto.randomUUID();
  localStorage.setItem("ag_user_id", id);
  return id;
}

export interface StoredSession {
  sessionId: string;
  userRequest: string;
  repoUrl?: string;
  startedAt: number;
  grade?: string;
  title?: string;
}

/**
 * Generates a clean, human-friendly title for a chat or codebase audit.
 * Always returns the user's starting message / prompt.
 * Never outputs `Audit · ...` or placeholder audit IDs.
 */
export function formatChatTitle(
  userRequest?: string,
  repoName?: string,
  sessionId?: string
): string {
  if (repoName && repoName.trim() && repoName.trim().toLowerCase() !== "general codebase audit") {
    return repoName.trim();
  }

  // If no user request or if it was previously set to an Audit ID placeholder, try to load from session view cache
  let prompt = userRequest?.trim() || "";
  if (
    (!prompt ||
      prompt.toLowerCase() === "new chat" ||
      prompt.toLowerCase() === "new audit" ||
      prompt.toLowerCase().startsWith("audit ·") ||
      prompt.toLowerCase().startsWith("audit ")) &&
    sessionId &&
    typeof window !== "undefined"
  ) {
    const cached = getSessionCache(sessionId);
    if (cached?.logs && cached.logs.length > 0) {
      const userLog = cached.logs.find(
        (l) =>
          l.author?.toLowerCase() === "user" ||
          (l as any).role === "user"
      );
      const text = userLog?.text || (userLog as any)?.message;
      if (text?.trim()) {
        prompt = text.trim();
      }
    }
  }

  if (
    !prompt ||
    prompt.toLowerCase() === "new chat" ||
    prompt.toLowerCase() === "new audit" ||
    prompt.toLowerCase().startsWith("audit ·") ||
    prompt.toLowerCase().startsWith("audit ")
  ) {
    return "New Chat";
  }

  // 1. Strip internal system notes and attachment markers
  let cleaned = prompt
    .replace(/\[System Note:[\s\S]*?\]/gi, "")
    .replace(/\(📎\s*[^)]+\)/gi, "")
    .replace(/📎\s*Attached:[^\n]+/gi, "")
    .trim();

  // 2. Check for github repo URL
  const ghMatch = (cleaned || prompt).match(/github\.com\/([^/\s]+)\/([^/\s#?]+)/i);
  if (ghMatch) {
    return `${ghMatch[1]}/${ghMatch[2].replace(/\.git$/i, "")}`;
  }

  // 3. If there is genuine user text prompt, use it directly
  if (cleaned) {
    const firstLine = cleaned.split("\n")[0].trim();
    if (firstLine) {
      const capitalized = firstLine.charAt(0).toUpperCase() + firstLine.slice(1);
      return capitalized.length > 40 ? capitalized.slice(0, 38) + "…" : capitalized;
    }
  }

  // 4. Check if user attached a ZIP file
  const zipPathMatch =
    prompt.match(/Temporarily preserved at [`'"]([^`'"]+)[`'"]/i) ||
    prompt.match(/ZIP file:\s*[`'"]?([^`'"\n\r\]]+)[`'"]?/i) ||
    prompt.match(/📎\s*([a-zA-Z0-9_\-. ]+\.zip)/i) ||
    prompt.match(/([a-zA-Z0-9_\-. ]+\.zip)/i);

  if (zipPathMatch && zipPathMatch[1]) {
    const rawPath = zipPathMatch[1].trim();
    const filename = rawPath.split(/[\\/]/).pop() || rawPath;
    if (filename) {
      if (/^tmp[a-z0-9_.-]+\.zip$/i.test(filename)) {
        return "Uploaded Codebase";
      }
      return filename;
    }
  }

  return "New Chat";
}


export function saveSession(session: StoredSession): void {
  if (typeof window === "undefined") return;
  const sessions = getSessions();
  const index = sessions.findIndex((s) => s.sessionId === session.sessionId);
  if (index >= 0) {
    const existing = sessions[index];
    // Preserve existing non-empty start message if incoming userRequest is empty or an Audit placeholder
    let userRequest = session.userRequest?.trim() ? session.userRequest.trim() : existing.userRequest;
    if (
      (!userRequest ||
        userRequest.toLowerCase() === "new chat" ||
        userRequest.toLowerCase() === "new audit" ||
        userRequest.toLowerCase().startsWith("audit ·") ||
        userRequest.toLowerCase().startsWith("audit ")) &&
      existing.userRequest &&
      !existing.userRequest.toLowerCase().startsWith("audit ·") &&
      !existing.userRequest.toLowerCase().startsWith("audit ")
    ) {
      userRequest = existing.userRequest;
    }

    sessions[index] = {
      ...existing,
      ...session,
      userRequest,
      startedAt: existing.startedAt || session.startedAt,
    };
  } else {
    sessions.unshift(session);
  }
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessions.slice(0, 50)));
  } catch (e) {
    console.warn("ag: failed to persist session list", e);
  }
}

export function getSessions(): StoredSession[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function setUserId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("ag_user_id", id.trim());
}

export interface UserProfile {
  userId: string;
  department: string;
  country: string;
}

/** The login profile, or null if it's incomplete (gate should show the form).
 * All three fields are required — a bare `ag_user_id` left over from the old
 * auto-generated UUID does NOT count as logged in. */
export function getUserProfile(): UserProfile | null {
  if (typeof window === "undefined") return null;
  const userId = localStorage.getItem("ag_user_id") ?? "";
  const department = localStorage.getItem("ag_user_department") ?? "";
  const country = localStorage.getItem("ag_user_country") ?? "";
  if (!userId || !department || !country) return null;
  return { userId, department, country };
}

export function setUserProfile(p: UserProfile): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("ag_user_id", p.userId.trim());
  localStorage.setItem("ag_user_department", p.department.trim());
  localStorage.setItem("ag_user_country", p.country.trim());
}

export function removeSession(sessionId: string): void {
  if (typeof window === "undefined") return;
  const updated = getSessions().filter((s) => s.sessionId !== sessionId);
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(updated));
}

export interface SessionViewCache {
  logs: Array<Omit<LogEntry, "rawEvent">>;
  phases: PipelinePhase[];
  state?: Record<string, unknown>;
  cachedAt: number;
}

export function cacheSessionView(
  sessionId: string,
  logs: LogEntry[],
  phases: PipelinePhase[],
  state?: Record<string, unknown>
): void {
  if (typeof window === "undefined") return;
  try {
    const stripped = logs.map(({ rawEvent: _raw, ...rest }) => rest);
    const payload = JSON.stringify({ logs: stripped, phases, state, cachedAt: Date.now() });
    if (payload.length > MAX_CACHE_BYTES) return;
    localStorage.setItem(`${SESSION_CACHE_PREFIX}${sessionId}`, payload);
  } catch {
    // localStorage full or unavailable — silently skip
  }
}

export function getSessionCache(sessionId: string): SessionViewCache | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(`${SESSION_CACHE_PREFIX}${sessionId}`);
    if (!raw) return null;
    return JSON.parse(raw) as SessionViewCache;
  } catch {
    return null;
  }
}

export function pruneSessionCaches(validIds: string[]): void {
  if (typeof window === "undefined") return;
  const valid = new Set(validIds);
  const toRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (key.startsWith(SESSION_CACHE_PREFIX)) {
      const sid = key.slice(SESSION_CACHE_PREFIX.length);
      if (!valid.has(sid)) toRemove.push(key);
    }
    if (key.startsWith(PAYLOAD_CACHE_PREFIX)) {
      const sid = key.slice(PAYLOAD_CACHE_PREFIX.length);
      if (!valid.has(sid)) toRemove.push(key);
    }
  }
  toRemove.forEach((k) => localStorage.removeItem(k));
}

/**
 * Logs out the active user and clears all workspace localStorage/sessionStorage
 * variables so that the login authentication gate is immediately presented.
 * Retains UI theme preference (`ag_theme`).
 */
export function logoutAndClearWorkspace(): void {
  if (typeof window === "undefined") return;

  // 1. Remove identity profile
  localStorage.removeItem("ag_user_id");
  localStorage.removeItem("ag_user_department");
  localStorage.removeItem("ag_user_country");
  localStorage.removeItem("ag_auth_token");
  localStorage.removeItem("ag_profile");

  // 2. Clear sessions and cached payloads
  localStorage.removeItem(SESSION_STORAGE_KEY);
  localStorage.removeItem("ag_active_session");

  // 3. Clear all cached session logs
  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (key.startsWith(SESSION_CACHE_PREFIX) || key.startsWith(PAYLOAD_CACHE_PREFIX)) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((k) => localStorage.removeItem(k));

  // 4. Clear transient sessionStorage
  try {
    sessionStorage.clear();
  } catch {
    // ignore
  }
}

export function getStoredAppName(): string {
  if (typeof window === "undefined") return process.env.NEXT_PUBLIC_ADK_APP_NAME || "agent_guardian";
  return localStorage.getItem("ag_adk_app_name") || process.env.NEXT_PUBLIC_ADK_APP_NAME || "agent_guardian";
}

export function setStoredAppName(name: string): void {
  if (typeof window === "undefined") return;
  const cleaned = (name || "").trim() || "agent_guardian";
  localStorage.setItem("ag_adk_app_name", cleaned);
}

export function getStoredAdkBaseUrl(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ag_adk_base_url") || "";
}

export function setStoredAdkBaseUrl(url: string): void {
  if (typeof window === "undefined") return;
  const cleaned = (url || "").trim();
  if (!cleaned) {
    localStorage.removeItem("ag_adk_base_url");
  } else {
    localStorage.setItem("ag_adk_base_url", cleaned);
  }
}

