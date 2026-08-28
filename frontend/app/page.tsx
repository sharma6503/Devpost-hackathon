"use client";

import { useEffect, useState, useRef, useCallback, Suspense, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  Code2,
  Cpu,
  CheckSquare,
  ArrowLeft,
  Files,
  Clock,
  ShieldAlert,
  RefreshCw,
  Plus,
  FileArchive,
  X,
  GitBranch,
  Upload,
  ArrowRight,
  ArrowUp,
  Square,
  Loader2,
  ShieldCheck,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Sparkles,
  MessageSquare,
  Settings,
  Copy,
  Check,
  Wrench,
  PanelLeft,
  PanelLeftClose,
  PanelTop,
  PanelTopClose,
  SlidersHorizontal,
  Share2,
  Layers,
  Search,
  Terminal,
  Zap,
  Bot,
  Paperclip,
} from "lucide-react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";

import { ChatLogRow, AGENT_LABELS_LOCAL } from "@/components/review/ChatLogRow";
import { RemediationBanner } from "@/components/results/RemediationBanner";

// ADK Clients & Session Helpers
import { createSession, getSession, deleteAdkSession, listSessions, listApps } from "@/lib/adk-client";
import {
  getSessions,
  generateUserId,
  generateSessionId,
  removeSession,
  saveSession,
  type StoredSession,
  setUserId as saveUserIdLocal,
  getUserProfile,
  getSessionCache,
  cacheSessionView,
  logoutAndClearWorkspace,
  formatChatTitle,
  getStoredAppName,
  setStoredAppName,
} from "@/lib/session";

// Review Hooks and Views
import { useAgentReview, type ReviewSeed } from "@/hooks/useAgentReview";
import { REMEDIATION_APPROVE_CMD, REMEDIATION_SKIP_CMD } from "@/lib/remediation";
import { formatElapsed } from "@/lib/format";

// Event Parser Helpers
import {
  applyEventInto,
  buildInitialPhases,
  finalizePhases,
  isDuplicateLog,
  toMillis,
  cleanGrade,
  reconstructSessionLogs,
  deepMergeState,
} from "@/lib/event-parser";

// User Console & Trace Bar
import { UserConsoleDrawer } from "@/components/console/UserConsoleDrawer";
import { UserTraceBar } from "@/components/review/UserTraceBar";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";
import { AuditSearchModal } from "@/components/review/AuditSearchModal";
import { EventInspectorModal } from "@/components/review/EventInspectorModal";

// Agent Guardian UI Components
import { GuardianSidebar, type EnrichedSessionItem } from "@/components/guardian/GuardianSidebar";
import { GuardianHeader } from "@/components/guardian/GuardianHeader";
import { ExportShareModal } from "@/components/guardian/ExportShareModal";

// ADK Types
import type { ReviewState, ReviewMetrics, Session, AdkEvent, LogEntry, PipelinePhase, Part } from "@/types/adk";

interface EnrichedSession extends StoredSession {
  grade?: "A" | "B" | "C" | "D" | "F";
  adkAlive?: boolean;
  lastUpdateTime?: number;
  sessionUserId?: string;
  status?: string;
}

const LOG_WINDOW = 80;

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1] || "";
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function Home() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen w-full items-center justify-center bg-white dark:bg-[#212121] text-black dark:text-white font-mono text-xs">
          <Loader2 className="h-5 w-5 animate-spin text-[#2525A3] mr-2" />
          Loading Agent Guardian...
        </div>
      }
    >
      <MainChatLayout />
    </Suspense>
  );
}

function MainChatLayout() {
  const searchParams = useSearchParams();
  const router = useRouter();

  // User Profile
  const [userId, setUserIdState] = useState<string>("demo-operator");
  const [userIdLocked, setUserIdLocked] = useState(false);

  // Dynamic ADK Apps
  const [availableApps, setAvailableApps] = useState<string[]>(["agent_guardian"]);
  const [activeAppName, setActiveAppName] = useState<string>("agent_guardian");

  useEffect(() => {
    const profile = getUserProfile();
    if (profile?.userId) {
      setUserIdState(profile.userId);
    }
    const storedApp = getStoredAppName();
    if (storedApp) {
      setActiveAppName(storedApp);
    }
    listApps()
      .then((apps) => {
        if (apps && apps.length > 0) {
          setAvailableApps((prev) => Array.from(new Set([...prev, ...apps])));
        }
      })
      .catch(() => {});
  }, []);

  const handleSelectApp = (appName: string) => {
    setActiveAppName(appName);
    setStoredAppName(appName);
    refreshSessions(userId, appName);
  };

  // Active Session
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Sidebar, Header, Inspector, Share & Search Modal States
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [headerVisible, setHeaderVisible] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [shareModalOpen, setShareModalOpen] = useState(false);

  // Global keydown shortcuts: Cmd+K / Ctrl+K for Search, Alt+H for Toggle Header
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchModalOpen((prev) => !prev);
      }
      if (e.altKey && e.key.toLowerCase() === "h") {
        e.preventDefault();
        setHeaderVisible((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Auto-close sidebar on small screens (< 768px)
  useEffect(() => {
    const handleResize = () => {
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        setSidebarOpen(false);
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Prompt Form State
  const [promptInput, setPromptInput] = useState("");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submissionError, setSubmissionError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Session History Management
  const [recentSessions, setRecentSessions] = useState<EnrichedSessionItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyOffline, setHistoryOffline] = useState(false);

  // Historical Session Data (when viewing past session)
  const [historicalSession, setHistoricalSession] = useState<Session | null>(null);
  const [sessionState, setSessionState] = useState<Partial<ReviewState> | null>(null);
  const [historicalLog, setHistoricalLog] = useState<LogEntry[]>([]);
  const [sessionLoadError, setSessionLoadError] = useState<string | null>(null);
  const [loadingHistoricalSession, setLoadingHistoricalSession] = useState(false);
  const [inspectingState, setInspectingState] = useState<Record<string, unknown> | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<AdkEvent | null>(null);

  // Synchronize active session ID in URL query parameter without full reload
  const syncSessionUrl = useCallback((sid?: string | null) => {
    if (typeof window === "undefined") return;
    try {
      const url = new URL(window.location.href);
      if (sid) {
        url.searchParams.set("sessionId", sid);
        url.searchParams.delete("session");
      } else {
        url.searchParams.delete("sessionId");
        url.searchParams.delete("session");
      }
      window.history.pushState({}, "", url.pathname + url.search);
    } catch {
      // ignore
    }
  }, []);

  // Live Audit Hook
  const {
    isRunning,
    log,
    phases,
    liveEntry,
    activeAgent,
    elapsedMs,
    sessionState: liveSessionState,
    start,
    stop,
    reset,
  } = useAgentReview();

  const elapsedSeconds = Math.floor(elapsedMs / 1000);

  const isReviewing = isRunning;
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when new logs arrive
  useEffect(() => {
    if (activeSessionId) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [log, liveEntry, activeSessionId]);

  // Persist live session updates to local cache and sync historicalLog
  useEffect(() => {
    if (activeSessionId && log.length > 0) {
      const finalState =
        liveSessionState && Object.keys(liveSessionState).length > 0
          ? liveSessionState
          : sessionState || undefined;

      cacheSessionView(activeSessionId, log, phases, finalState);
      setHistoricalLog(log);
      if (liveSessionState && Object.keys(liveSessionState).length > 0) {
        setSessionState(liveSessionState);
      }
      const grade = cleanGrade(liveSessionState?.evaluation_grade);
      const existing =
        getSessions().find((s) => s.sessionId === activeSessionId) ||
        recentSessions.find((s) => s.sessionId === activeSessionId);
      const firstUserLog = log.find(
        (l) => l.author?.toLowerCase() === "user" || (l as any).role === "user"
      );
      const userReq =
        existing?.userRequest ||
        firstUserLog?.text ||
        (firstUserLog as any)?.message ||
        (liveSessionState?.user_request as string) ||
        "";

      saveSession({
        sessionId: activeSessionId,
        userRequest: userReq,
        startedAt: existing?.startedAt || Date.now(),
        lastUpdateTime: Date.now(),
        grade: grade as any,
        userId,
        appName: activeAppName,
      });
    }
  }, [log, phases, liveSessionState, activeSessionId, recentSessions, userId, activeAppName, sessionState]);

  // Read URL Params (session & userId)
  useEffect(() => {
    const rawSid = searchParams.get("sessionId") || searchParams.get("session");
    const uId = searchParams.get("userId");
    if (uId) {
      setUserIdState(uId);
      saveUserIdLocal(uId);
      setUserIdLocked(true);
    }
    if (rawSid) {
      const sId = decodeURIComponent(rawSid.trim());
      if (sId && sId !== activeSessionId) {
        setActiveSessionId(sId);
        loadHistoricalSession(uId || userId, sId, activeAppName);
      }
    }
  }, [searchParams]);

  // Load Sessions List
  const refreshSessions = useCallback(async (currentUserId: string, appName?: string) => {
    setLoadingHistory(true);
    setHistoryOffline(false);
    const targetApp = appName || activeAppName;
    try {
      const local = getSessions();
      const res = await listSessions(currentUserId, targetApp).catch(() => null);

      if (res && Array.isArray(res)) {
        const enriched: EnrichedSessionItem[] = res.map((s) => {
          const match = local.find((l) => l.sessionId === s.id);
          const rawGrade = (s.state?.evaluation_grade as string) || match?.grade;
          const grade = cleanGrade(rawGrade);
          const scores = (s.state?.review_metrics as any)?.scores;

          // Resolve starting message from all available sources
          let userReq = match?.userRequest?.trim() || (s.state?.user_request as string)?.trim() || "";

          // Check if userReq was previously a placeholder or empty
          if (!userReq || userReq.toLowerCase().startsWith("audit ·") || userReq.toLowerCase().startsWith("audit ")) {
            userReq = "";
          }

          // Inspect session events for user prompt
          if (!userReq && s.events && Array.isArray(s.events)) {
            for (const ev of s.events) {
              if (ev.author === "user" || ev.content?.role === "user" || !ev.author) {
                const parts = ev.content?.parts;
                if (Array.isArray(parts)) {
                  for (const p of parts) {
                    if (p.text && p.text.trim()) {
                      userReq = p.text.trim();
                      break;
                    }
                    if (p.inlineData?.displayName || p.inline_data?.displayName) {
                      userReq = p.inlineData?.displayName || p.inline_data?.displayName || "";
                      break;
                    }
                  }
                }
              }
              if (userReq) break;
            }
          }

          // Inspect local cached logs
          if (!userReq) {
            const cached = getSessionCache(s.id);
            if (cached?.logs && cached.logs.length > 0) {
              const userLog = cached.logs.find(
                (l) => l.author?.toLowerCase() === "user" || (l as any).role === "user"
              );
              const text = userLog?.text || (userLog as any)?.message;
              if (text?.trim()) {
                userReq = text.trim();
              }
            }
          }

          // If we found a valid starting message, persist it to localStorage
          if (userReq) {
            saveSession({
              sessionId: s.id,
              userRequest: userReq,
              startedAt: match?.startedAt || toMillis(s.lastUpdateTime || 0) || Date.now(),
              lastUpdateTime: toMillis(s.lastUpdateTime || 0) || match?.startedAt || Date.now(),
              grade: grade as any,
              userId: currentUserId,
              appName: targetApp,
            });
          }

          return {
            sessionId: s.id,
            userRequest: userReq,
            startedAt: match?.startedAt || toMillis(s.lastUpdateTime || 0) || Date.now(),
            lastUpdateTime: toMillis(s.lastUpdateTime || 0) || match?.startedAt || Date.now(),
            grade,
            securityScore: scores?.security,
            criticalIssues: (s.state?.review_metrics as any)?.severity?.critical,
            adkAlive: true,
            status: isRunning && activeSessionId === s.id ? "ACTIVE" : undefined,
          };
        });

        // Also merge any local-only sessions that aren't in remote list
        const remoteIds = new Set(res.map((s) => s.id));
        for (const loc of local) {
          if (!remoteIds.has(loc.sessionId)) {
            enriched.push({
              sessionId: loc.sessionId,
              userRequest: loc.userRequest,
              startedAt: loc.startedAt,
              lastUpdateTime: loc.lastUpdateTime || loc.startedAt,
              grade: cleanGrade(loc.grade),
              adkAlive: false,
              status: isRunning && activeSessionId === loc.sessionId ? "ACTIVE" : undefined,
            });
          }
        }

        enriched.sort((a, b) => {
          const timeA = a.lastUpdateTime || a.startedAt || 0;
          const timeB = b.lastUpdateTime || b.startedAt || 0;
          return timeB - timeA;
        });
        setRecentSessions(enriched);
      } else {
        // Fallback to localStorage
        const enriched: EnrichedSessionItem[] = local
          .map((s) => {
            let userReq = s.userRequest?.trim() || "";
            if (!userReq || userReq.toLowerCase().startsWith("audit ·") || userReq.toLowerCase().startsWith("audit ")) {
              const cached = getSessionCache(s.sessionId);
              const userLog = cached?.logs?.find(
                (l) => l.author?.toLowerCase() === "user" || (l as any).role === "user"
              );
              const text = userLog?.text || (userLog as any)?.message;
              if (text?.trim()) {
                userReq = text.trim();
              }
            }

            return {
              sessionId: s.sessionId,
              userRequest: userReq,
              startedAt: s.startedAt,
              lastUpdateTime: s.lastUpdateTime || s.startedAt,
              grade: cleanGrade(s.grade),
              adkAlive: false,
              status: isRunning && activeSessionId === s.sessionId ? "ACTIVE" : undefined,
            };
          })
          .sort((a, b) => {
            const timeA = a.lastUpdateTime || a.startedAt || 0;
            const timeB = b.lastUpdateTime || b.startedAt || 0;
            return timeB - timeA;
          });
        setRecentSessions(enriched);
        setHistoryOffline(true);
      }
    } catch {
      setHistoryOffline(true);
    } finally {
      setLoadingHistory(false);
    }
  }, [isRunning, activeSessionId, activeAppName]);

  useEffect(() => {
    refreshSessions(userId, activeAppName);
  }, [userId, activeAppName, refreshSessions]);

  // Load a Historical Session
  const loadHistoricalSession = async (uid: string, sid: string, appName?: string) => {
    setSessionLoadError(null);
    setLoadingHistoricalSession(true);
    const stored = getSessions().find((s) => s.sessionId === sid);
    const effectiveUid = stored?.userId || uid || userId;
    const targetApp = stored?.appName || appName || activeAppName;
    const cached = getSessionCache(sid);

    // If we have cached logs or state in localStorage, restore them immediately
    if (cached?.logs && cached.logs.length > 0) {
      setHistoricalLog(cached.logs as LogEntry[]);
    }
    if (cached?.state && Object.keys(cached.state).length > 0) {
      setSessionState(cached.state);
    }

    try {
      // Try to fetch or create the session on ADK backend
      const sess = await getSession(effectiveUid, sid, targetApp).catch(async (fetchErr) => {
        // If 404 (ADK in-memory restart or stale session), create/register on backend
        if (fetchErr?.message?.includes("404")) {
          return await createSession(effectiveUid, sid, undefined, targetApp).catch(() => null);
        }
        return null;
      });

      if (sess) {
        setHistoricalSession(sess);
        const mergedState = deepMergeState(cached?.state || {}, sess.state || {});
        if (sess.events && sess.events.length > 0) {
          const { logs, phases: reconPhases, sessionState: reconState } = reconstructSessionLogs(
            sess.events,
            mergedState
          );
          const finalState = deepMergeState(mergedState, reconState);
          const finalLogs = logs.length > 0 ? logs : ((cached?.logs as LogEntry[]) || []);
          setHistoricalLog(finalLogs);
          setSessionState(finalState);
          cacheSessionView(sid, finalLogs, reconPhases, finalState);
        } else {
          if (Object.keys(mergedState).length > 0) {
            setSessionState(mergedState);
          }
          if (!cached?.logs || cached.logs.length === 0) {
            setHistoricalLog([]);
          }
        }
      } else if (!cached?.logs) {
        setHistoricalLog([]);
      }
    } catch (err: any) {
      console.warn("Could not sync historical session with backend:", err);
      if (!cached?.logs) {
        setSessionLoadError("Backend server is unreachable. Offline mode active.");
      }
    } finally {
      setLoadingHistoricalSession(false);
    }
  };

  // Switch Active Session
  const handleSelectSession = (sid: string) => {
    reset();
    setActiveSessionId(sid);
    syncSessionUrl(sid);
    loadHistoricalSession(userId, sid, activeAppName);
  };

  // Delete a Session
  const handleDeleteSession = async (sid: string) => {
    try {
      const stored = getSessions().find((s) => s.sessionId === sid);
      const targetUid = stored?.userId || userId;
      const targetApp = stored?.appName || activeAppName;
      await deleteAdkSession(targetUid, sid, targetApp).catch(() => null);
      removeSession(sid);
      if (activeSessionId === sid) {
        handleNewAuditSession();
      }
      refreshSessions(userId, activeAppName);
    } catch (err) {
      console.error("Delete session error:", err);
    }
  };

  // Create New Session / New Chat
  const handleNewAuditSession = () => {
    reset();
    setActiveSessionId(null);
    setHistoricalSession(null);
    setSessionState(null);
    setHistoricalLog([]);
    setPromptInput("");
    setUploadedFile(null);
    setSubmissionError("");
    syncSessionUrl(null);
  };

  // Submit Prompt to Start or Continue Audit
  const handleAuditSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (submitting) return;

    if (isRunning) {
      // User clicked stop
      stop();
      return;
    }

    const trimmed = promptInput.trim();
    const fileToUpload = uploadedFile;
    if (!trimmed && !fileToUpload) {
      setSubmissionError("Please provide an audit instruction, GitHub repo URL, or attach a ZIP file.");
      return;
    }

    // Immediately clear input and attachment so the input bar is empty during processing
    setPromptInput("");
    setUploadedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    setSubmitting(true);
    setSubmissionError("");

    try {
      let repoUrl = "";
      const ghMatch = trimmed.match(/https?:\/\/github\.com\/[^\s]+/i);
      if (ghMatch) {
        repoUrl = ghMatch[0];
      }

      let zipBase64 = "";
      if (fileToUpload) {
        zipBase64 = await fileToBase64(fileToUpload);
      }

      const newSessionId = activeSessionId || generateSessionId();
      setActiveSessionId(newSessionId);

      const mimeType = fileToUpload?.name.toLowerCase().endsWith(".zip")
        ? "application/zip"
        : fileToUpload?.type || "application/zip";

      const inlineFiles = zipBase64
        ? [
            {
              displayName: fileToUpload?.name || "codebase.zip",
              data: zipBase64,
              mimeType,
            },
          ]
        : undefined;

      // Save session in local cache with both prompt and attached file
      saveSession({
        sessionId: newSessionId,
        userRequest: trimmed
          ? fileToUpload
            ? `${trimmed} (📎 ${fileToUpload.name})`
            : trimmed
          : fileToUpload?.name || "Codebase Audit",
        startedAt: Date.now(),
      });

      const userDisplayMessage = fileToUpload
        ? trimmed
          ? `${trimmed}\n\n📎 Attached: \`${fileToUpload.name}\``
          : `📎 Attached: \`${fileToUpload.name}\``
        : trimmed;

      const currentLogs = log.length > 0 ? log : historicalLog;
      const currentPhases = phases;
      const currentSessionStateVal =
        liveSessionState && Object.keys(liveSessionState).length > 0
          ? liveSessionState
          : sessionState || {};

      // Launch Multi-Agent Swarm with seed so existing conversation is preserved
      await start(
        {
          userId,
          sessionId: newSessionId,
          messageText: trimmed || ` ${fileToUpload?.name || "codebase.zip"}`,
          displayText: userDisplayMessage,
          appName: activeAppName,
          inlineFiles,
        },
        currentLogs.length > 0
          ? {
              log: currentLogs,
              phases: currentPhases,
              sessionState: currentSessionStateVal,
            }
          : undefined
      );

      refreshSessions(userId, activeAppName);
    } catch (err: any) {
      setSubmissionError(err.message || "Failed to initiate agent execution");
    } finally {
      setSubmitting(false);
    }
  };

  // Remediation Approvals
  const sendRemediationDecision = async (approved: boolean) => {
    if (!activeSessionId) return;
    const cmd = approved ? REMEDIATION_APPROVE_CMD : REMEDIATION_SKIP_CMD;
    const currentLogs = log.length > 0 ? log : historicalLog;
    const currentPhases = phases;
    const currentSessionStateVal =
      liveSessionState && Object.keys(liveSessionState).length > 0
        ? liveSessionState
        : sessionState || {};

    await start(
      {
        userId,
        sessionId: activeSessionId,
        messageText: cmd,
        displayText: approved ? "Approve Remediation Plan" : "Skip Remediation",
        appName: activeAppName,
      },
      currentLogs.length > 0
        ? {
            log: currentLogs,
            phases: currentPhases,
            sessionState: currentSessionStateVal,
          }
        : undefined
    );
  };

  const activeLogs = log.length > 0 ? log : historicalLog;
  const currentSessionState =
    liveSessionState && Object.keys(liveSessionState).length > 0
      ? liveSessionState
      : sessionState;

  const currentActiveSession = recentSessions.find((s) => s.sessionId === activeSessionId);
  const activeChatTitle = formatChatTitle(
    currentActiveSession?.userRequest || promptInput,
    currentActiveSession?.repoName,
    activeSessionId ?? undefined
  );

  const handleLogout = () => {
    logoutAndClearWorkspace();
    window.location.reload();
  };

  return (
    <div className="flex h-screen w-full bg-white dark:bg-[#212121] text-black dark:text-[#ECECF1] font-sans overflow-hidden transition-colors duration-200">
      {/* ─── 1. Agent Guardian Left Sidebar ─── */}
      <GuardianSidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        sessions={recentSessions}
        activeSessionId={activeSessionId ?? undefined}
        userId={userId}
        loading={loadingHistory}
        offline={historyOffline}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewSession={handleNewAuditSession}
        onOpenTelemetry={() => setInspectorOpen(true)}
        onOpenSearch={() => setSearchModalOpen(true)}
        onLogout={handleLogout}
        onSaveUserId={(newId) => {
          setUserIdState(newId);
          saveUserIdLocal(newId);
          refreshSessions(newId, activeAppName);
        }}
        editableUser={!userIdLocked}
      />

      {/* ─── 2. Main Guardian Canvas ─── */}
      <div
        className={`flex-1 flex flex-col h-full min-w-0 transition-all duration-300 ${
          sidebarOpen ? "md:ml-[280px]" : "md:ml-[60px]"
        }`}
      >
        {/* ─── Guardian Top Section (Header + Trace Ribbon - Collapsible) ─── */}
        {headerVisible ? (
          <>
            <GuardianHeader
              isSidebarOpen={sidebarOpen}
              onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
              headerVisible={headerVisible}
              onToggleHeader={() => setHeaderVisible(false)}
              activeSessionId={activeSessionId ?? undefined}
              activeRepo={currentActiveSession?.repoName || currentActiveSession?.userRequest}
              availableApps={availableApps}
              activeAppName={activeAppName}
              onSelectApp={handleSelectApp}
              onToggleInspector={() => setInspectorOpen(!inspectorOpen)}
              onOpenSearch={() => setSearchModalOpen(true)}
              onOpenShare={() => setShareModalOpen(true)}
              inspectorOpen={inspectorOpen}
              isRunning={isRunning}
            />

            {/* ─── Interactive User Trace Ribbon Bar ─── */}
            {(activeSessionId !== null || isRunning || activeLogs.length > 0) && (
              <UserTraceBar
                chatTitle={activeChatTitle}
                isRunning={isRunning}
                activeAgent={activeAgent}
                activePhase={isRunning ? "Analyzing Execution" : "Ready"}
                elapsedSeconds={elapsedSeconds}
                sessionState={currentSessionState || {}}
                logCount={activeLogs.length}
                onOpenConsole={() => setInspectorOpen(true)}
                onOpenArtifacts={() => setInspectorOpen(true)}
              />
            )}
          </>
        ) : (
          /* ─── Top-Right Floating Restore Toggle Bar (when full top section is hidden) ─── */
          <div className="sticky top-2 z-30 flex justify-end px-3 sm:px-6 pointer-events-none mb-1">
            <div className="pointer-events-auto flex items-center gap-1.5 p-1 bg-white/95 dark:bg-[#212121]/95 backdrop-blur-md border border-black/10 dark:border-white/10 rounded-xl shadow-md animate-in fade-in slide-in-from-top-1 duration-150">
              <button
                onClick={() => setHeaderVisible(true)}
                className="p-1.5 rounded-lg bg-[#2525A3]/10 dark:bg-[#2525A3]/20 hover:bg-[#2525A3] hover:text-white dark:hover:bg-[#2525A3] text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/30 hover:border-[#2525A3] transition-all cursor-pointer shadow-2xs group"
                title="Show Header (Alt+H)"
                aria-label="Show Header"
              >
                <ChevronDown className="h-4 w-4 group-hover:text-white transition-colors" />
              </button>

              <button
                onClick={() => setSearchModalOpen(true)}
                className="p-1.5 rounded-lg border border-black/10 dark:border-white/10 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 text-xs cursor-pointer transition-colors"
                title="Search audits (⌘K)"
                aria-label="Search audits"
              >
                <Search className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setInspectorOpen(!inspectorOpen)}
                className={`flex items-center gap-1 px-2 py-1 rounded-lg border transition-colors cursor-pointer text-xs ${
                  inspectorOpen
                    ? "bg-[#2525A3] text-white border-[#2525A3]"
                    : "border-black/10 dark:border-white/10 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5"
                }`}
                title="Toggle Console"
                aria-label="Toggle Console"
              >
                <SlidersHorizontal className="h-3 w-3" />
                <span className="hidden sm:inline text-[11px]">Console</span>
              </button>
            </div>
          </div>
        )}

        {/* Center Main View Area */}
        <div className="flex-1 flex min-h-0 relative">
          {/* Main Chat Stream Container */}
          <main className="flex-1 flex flex-col h-full min-w-0 overflow-hidden relative">
            <div className="flex-1 overflow-y-auto custom-scrollbar px-3 sm:px-6 md:px-8 py-4 sm:py-6">
              <div className="max-w-3xl mx-auto w-full space-y-6">
                {/* ─── Empty / Welcome Hero State ─── */}
                {activeSessionId === null && (
                  <div className="flex flex-col items-center justify-center py-12 md:py-20 text-center animate-fade-in">
                    {/* Agent Guardian Logo */}
                    <AgentGuardianLogo size={64} priority className="mb-6" />

                    <h1 className="text-xl md:text-2xl font-headline font-bold text-black dark:text-white mb-2 tracking-tight">
                      What would you like to audit today?
                    </h1>
                    <p className="text-xs md:text-sm text-[#737373] dark:text-[#8E8EA0] max-w-lg mb-4 leading-relaxed font-sans">
                      Autonomous multi-agent review for code security, framework compliance, and quality.
                    </p>
                  </div>
                )}

                {/* ─── Active Message Stream ─── */}
                {activeSessionId !== null && (
                  <div className="space-y-4">
                    {/* Error Banner */}
                    {!isReviewing && sessionLoadError && (
                      <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/30 text-xs text-red-500 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
                          <span>{sessionLoadError}</span>
                        </div>
                        <button
                          onClick={() => loadHistoricalSession(userId, activeSessionId)}
                          className="px-3 py-1 rounded-lg bg-red-500 hover:bg-red-600 text-white font-semibold transition-colors shrink-0 cursor-pointer"
                        >
                          Retry
                        </button>
                      </div>
                    )}

                    {/* Historical Session Loading Indicator */}
                    {loadingHistoricalSession && activeLogs.length === 0 && (
                      <div className="flex flex-col items-center justify-center py-16 text-center animate-fade-in space-y-3">
                        <Loader2 className="h-6 w-6 animate-spin text-[#2525A3] dark:text-[#A6C3EE]" />
                        <span className="text-xs text-[#737373] dark:text-[#8E8EA0] font-mono">
                          Restoring audit workspace & session history...
                        </span>
                      </div>
                    )}

                    {/* Empty session state */}
                    {!loadingHistoricalSession && activeLogs.length === 0 && !isReviewing && !sessionLoadError && (
                      <div className="flex flex-col items-center justify-center py-16 text-center text-xs text-[#737373] dark:text-[#8E8EA0] font-mono">
                        No messages found in this session. Start by entering a prompt below.
                      </div>
                    )}

                    {/* Messages */}
                    {activeLogs.map((entry) => (
                      <ChatLogRow
                        key={entry.id}
                        entry={entry}
                        onInspectDelta={(ev) => {
                          setInspectingState(ev.actions?.stateDelta ?? null);
                          setSelectedEvent(ev);
                          setInspectorOpen(true);
                        }}
                        onInspectEvent={(ev) => {
                          setSelectedEvent(ev);
                          setInspectorOpen(true);
                        }}
                        onApproveRemediation={() => sendRemediationDecision(true)}
                        onSkipRemediation={() => sendRemediationDecision(false)}
                      />
                    ))}

                    {/* Streaming Output */}
                    {liveEntry && (
                      <ChatLogRow
                        entry={liveEntry}
                        isStreaming={true}
                        onInspectDelta={(ev) => {
                          setSelectedEvent(ev);
                          setInspectorOpen(true);
                        }}
                        onInspectEvent={(ev) => {
                          setSelectedEvent(ev);
                          setInspectorOpen(true);
                        }}
                        onApproveRemediation={() => sendRemediationDecision(true)}
                        onSkipRemediation={() => sendRemediationDecision(false)}
                      />
                    )}

                    {/* Remediation Status Banner */}
                    {((currentSessionState?.remediation_status === "pending_approval" &&
                      !activeLogs.some(
                        (l) =>
                          l.author === "remediation_planner" ||
                          (typeof l.text === "string" &&
                            (l.text.includes('"pr_title"') || l.text.includes("Proposed Remediation Plan")))
                      )) ||
                      currentSessionState?.remediation_status === "created" ||
                      Boolean(currentSessionState?.remediation_pr_url)) && (
                      <div className="my-3 px-2">
                        <RemediationBanner
                          prUrl={currentSessionState?.remediation_pr_url}
                          status={currentSessionState?.remediation_status as any}
                          planSummary={currentSessionState?.remediation_plan_summary}
                          onApprove={() => sendRemediationDecision(true)}
                          onSkip={() => sendRemediationDecision(false)}
                          busy={isRunning}
                        />
                      </div>
                    )}

                    {/* Thinking Indicator */}
                    {isRunning && !liveEntry && (
                      <div className="flex items-center gap-3 p-3 text-xs text-[#737373] dark:text-[#8E8EA0] animate-pulse font-mono">
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#2525A3] text-white">
                          <Bot className="h-3.5 w-3.5" />
                        </div>
                        <span>
                          {activeAgent
                            ? `${AGENT_LABELS_LOCAL[activeAgent]?.label ?? activeAgent} is analyzing codebase...`
                            : "Agent Guardian swarm coordinating AST analysis..."}
                        </span>
                      </div>
                    )}

                    <div ref={messagesEndRef} className="h-4" />
                  </div>
                )}
              </div>
            </div>

            {/* ─── 3. Floating Prompt Bar ─── */}
            <div className="shrink-0 w-full max-w-3xl mx-auto px-3 sm:px-4 pb-3 sm:pb-4 pt-1.5">
              <form
                onSubmit={handleAuditSubmit}
                className="relative flex flex-col p-2 rounded-3xl bg-[#F4F4F4] dark:bg-[#2F2F2F] border border-black/10 dark:border-white/15 focus-within:border-black/30 dark:focus-within:border-white/30 shadow-xl transition-all"
              >
                {/* Attached File Badge */}
                {uploadedFile && (
                  <div className="flex items-center gap-2 self-start bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 px-3 py-1 rounded-xl mb-2 text-xs font-mono text-black dark:text-[#ECECF1]">
                    <FileArchive className="h-3.5 w-3.5 text-[#2525A3]" />
                    <span className="truncate max-w-xs">{uploadedFile.name}</span>
                    <span className="text-[#737373] dark:text-[#8E8EA0]">
                      ({(uploadedFile.size / 1024 / 1024).toFixed(1)} MB)
                    </span>
                    <button
                      type="button"
                      onClick={() => setUploadedFile(null)}
                      className="text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white ml-1 cursor-pointer"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )}

                {/* Main Input Row */}
                <div className="flex items-center gap-2 px-2">
                  {/* File Upload / Attachment Button */}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="p-2 rounded-full text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 transition-colors shrink-0 cursor-pointer"
                    title="Attach ZIP codebase"
                    aria-label="Attach ZIP codebase"
                  >
                    <Plus className="h-5 w-5" />
                  </button>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) {
                        setUploadedFile(f);
                        setSubmissionError("");
                      }
                    }}
                  />

                  {/* Auto-expanding Input Field */}
                  <input
                    type="text"
                    value={promptInput}
                    onChange={(e) => {
                      setPromptInput(e.target.value);
                      setSubmissionError("");
                    }}
                    placeholder="Message Agent Guardian or paste a GitHub repo URL..."
                    className="flex-1 bg-transparent border-0 outline-none text-xs sm:text-sm text-black dark:text-[#ECECF1] placeholder-[#737373] dark:placeholder-[#8E8EA0] py-2 px-1 font-sans"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleAuditSubmit();
                      }
                    }}
                  />

                  {/* Circular Send / Stop Button */}
                  <button
                    type="submit"
                    disabled={submitting || (!isRunning && !promptInput.trim() && !uploadedFile)}
                    className={`h-8 w-8 rounded-full flex items-center justify-center transition-all shrink-0 ${
                      isRunning
                        ? "bg-black dark:bg-white text-white dark:text-black cursor-pointer shadow-md"
                        : promptInput.trim() || uploadedFile
                        ? "bg-black dark:bg-white hover:bg-slate-800 dark:hover:bg-slate-200 text-white dark:text-black shadow-md cursor-pointer"
                        : "bg-black/10 dark:bg-white/10 text-[#737373] dark:text-[#8E8EA0] cursor-not-allowed"
                    }`}
                    title={isRunning ? "Stop generating" : "Send message"}
                  >
                    {submitting ? (
                      <Loader2 className="h-4 w-4 animate-spin text-white dark:text-black" />
                    ) : isRunning ? (
                      <Square className="h-3 w-3 fill-current text-white dark:text-black" />
                    ) : (
                      <ArrowUp className="h-4 w-4" />
                    )}
                  </button>
                </div>

                {submissionError && (
                  <div className="px-3 py-1 text-[11px] text-red-500 font-sans">
                    {submissionError}
                  </div>
                )}
              </form>

              {/* Disclaimer Footer */}
              <p className="text-center text-[11px] text-[#737373] dark:text-[#8E8EA0] pt-2 select-none font-sans">
                Agent Guardian can make mistakes. Verify important security, IAM, and architectural findings.
              </p>
            </div>
          </main>

          {/* ─── 4. User Mission Control Console Drawer ─── */}
          <UserConsoleDrawer
            isOpen={inspectorOpen}
            onClose={() => setInspectorOpen(false)}
            sessionState={currentSessionState || {}}
            selectedEvent={selectedEvent}
            log={activeLogs}
            isRunning={isRunning}
            userId={userId}
            activeSessionId={activeSessionId}
            sessions={recentSessions}
            sessionsLoading={loadingHistory}
            sessionsOffline={historyOffline}
            onSelectSession={handleSelectSession}
            onDeleteSession={handleDeleteSession}
            onNewSession={handleNewAuditSession}
            onInspectEvent={(evt) => setSelectedEvent(evt)}
          />

          {/* ─── 5. Spotlight Audit Search Modal (⌘K / Ctrl+K) ─── */}
          <AuditSearchModal
            isOpen={searchModalOpen}
            onClose={() => setSearchModalOpen(false)}
            sessions={recentSessions}
            activeSessionId={activeSessionId ?? undefined}
            onSelectSession={handleSelectSession}
            onNewSession={handleNewAuditSession}
          />

          {/* ─── 6. Raw ADK Event Inspector Modal ─── */}
          <EventInspectorModal
            isOpen={Boolean(selectedEvent)}
            event={selectedEvent}
            onClose={() => setSelectedEvent(null)}
          />

          {/* ─── 7. Export & Share Audit Modal ─── */}
          <ExportShareModal
            isOpen={shareModalOpen}
            onClose={() => setShareModalOpen(false)}
            sessionId={activeSessionId || "active-audit"}
            repoUrl={currentActiveSession?.repoName || currentActiveSession?.userRequest || ""}
            markdownContent={currentSessionState?.synthesis_result || currentSessionState?.evaluation_result || currentSessionState?.governance_review_result || ""}
            telemetryJson={currentSessionState || {}}
          />
        </div>
      </div>
    </div>
  );
}

