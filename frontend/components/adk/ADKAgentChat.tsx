"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Sparkles,
  ArrowUp,
  Paperclip,
  X,
  AlertCircle,
  HelpCircle,
  Shield,
  Layers,
  Terminal,
  Cpu,
  PanelLeft,
  PanelTop,
  PanelTopClose,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal,
} from "lucide-react";
import { GuardianSidebar, type EnrichedSessionItem } from "@/components/guardian/GuardianSidebar";
import { GuardianHeader } from "@/components/guardian/GuardianHeader";
import { ChatLogRow } from "@/components/review/ChatLogRow";
import { UserTraceBar } from "@/components/review/UserTraceBar";
import { UserConsoleDrawer } from "@/components/console/UserConsoleDrawer";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";
import { useAgentReview } from "@/hooks/useAgentReview";
import {
  listSessions,
  deleteAdkSession,
  getSession,
  createSession,
  getArtifact,
  listArtifacts,
} from "@/lib/adk-client";
import {
  saveSession,
  getSessions,
  removeSession,
  generateSessionId,
  getUserProfile,
  getSessionCache,
  cacheSessionView,
  type StoredSession,
} from "@/lib/session";
import { reconstructSessionLogs, deepMergeState } from "@/lib/event-parser";
import { REMEDIATION_APPROVE_CMD, REMEDIATION_SKIP_CMD } from "@/lib/remediation";
import type { LogEntry, Session, AdkEvent, ReviewState } from "@/types/adk";

export interface ADKAgentChatProps {
  /** The ADK app name registered on the backend (default: "agent_guardian") */
  appName?: string;
  /** Display title in header and assistant label (default: "Agent Guardian") */
  agentTitle?: string;
  /** Custom base API endpoint (default: "/api/adk") */
  apiBaseUrl?: string;
  /** User identifier (default: "demo-operator") */
  userId?: string;
  /** Optional initial session ID to load */
  initialSessionId?: string;
  /** Show the left sidebar for conversation history (default: true) */
  showSidebar?: boolean;
  /** Show the top telemetry ribbon bar (default: true) */
  showTraceBar?: boolean;
  /** Show the Mission Control Console drawer (default: true) */
  showConsole?: boolean;
  /** Optional placeholder for the prompt input */
  inputPlaceholder?: string;
  /** Custom CSS class names for the outer container */
  className?: string;
}

export function ADKAgentChat({
  appName = "agent_guardian",
  agentTitle = "Agent Guardian",
  apiBaseUrl = "/api/adk",
  userId: initialUserId = "demo-operator",
  initialSessionId,
  showSidebar = true,
  showTraceBar = true,
  showConsole = true,
  inputPlaceholder,
  className = "",
}: ADKAgentChatProps) {
  // User Profile
  const [userId, setUserIdState] = useState<string>(initialUserId);

  useEffect(() => {
    const profile = getUserProfile();
    if (profile?.userId) {
      setUserIdState(profile.userId);
    }
  }, []);

  // Active Session
  const [activeSessionId, setActiveSessionId] = useState<string | null>(
    initialSessionId ?? null
  );

  // Sidebar, Header & Inspector Drawer States
  const [sidebarOpen, setSidebarOpen] = useState(showSidebar);
  const [headerVisible, setHeaderVisible] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  // Global keydown shortcut for Alt+H
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
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

  // Historical Session Data (when viewing past session)
  const [historicalSession, setHistoricalSession] = useState<Session | null>(null);
  const [sessionState, setSessionState] = useState<Partial<ReviewState> | null>(null);
  const [historicalLog, setHistoricalLog] = useState<LogEntry[]>([]);

  // Telemetry drawer selected tab
  const [inspectorActiveTab, setInspectorActiveTab] = useState<
    "overview" | "tool_calls" | "raw_events" | "state_deltas"
  >("overview");

  // Bottom scroll anchor
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Core ADK Streaming Hook
  const {
    phases,
    activeAgent,
    log: activeLogs,
    liveEntry,
    sessionState: hookState,
    isRunning,
    isComplete,
    error: hookError,
    elapsedMs,
    start: startAgentReview,
    reset: resetAgentReview,
  } = useAgentReview();

  // Scroll to bottom on new messages or streaming
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeLogs, liveEntry, historicalLog]);

  // Load Session History
  const refreshHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const stored = getSessions();
      const enriched: EnrichedSessionItem[] = stored
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
            lastUpdateTime: s.startedAt,
            grade: s.grade,
          };
        })
        .sort((a, b) => (b.lastUpdateTime || b.startedAt || 0) - (a.lastUpdateTime || a.startedAt || 0));
      setRecentSessions(enriched);
    } catch {
      setRecentSessions([]);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  // Load Historical Session
  const loadHistoricalSession = useCallback(
    async (sid: string) => {
      const stored = getSessions().find((s) => s.sessionId === sid);
      const targetUid = stored?.userId || userId;
      const targetApp = stored?.appName || appName;
      const cached = getSessionCache(sid);

      if (cached?.logs && cached.logs.length > 0) {
        setHistoricalLog(cached.logs as LogEntry[]);
      }
      if (cached?.state && Object.keys(cached.state).length > 0) {
        setSessionState(cached.state);
      }

      try {
        const sess = await getSession(targetUid, sid, targetApp).catch(async (fetchErr) => {
          if (fetchErr?.message?.includes("404")) {
            return await createSession(targetUid, sid, undefined, targetApp).catch(() => null);
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
          }
        }
      } catch (err) {
        console.warn("Could not fetch historical session:", err);
      }
    },
    [userId, appName]
  );

  useEffect(() => {
    if (initialSessionId) {
      loadHistoricalSession(initialSessionId);
    }
  }, [initialSessionId, loadHistoricalSession]);

  // Handle Select Session
  const handleSelectSession = useCallback(
    (sid: string) => {
      resetAgentReview();
      setActiveSessionId(sid);
      loadHistoricalSession(sid);
    },
    [resetAgentReview, loadHistoricalSession]
  );

  // Handle New Chat
  const handleNewChat = useCallback(() => {
    resetAgentReview();
    setActiveSessionId(null);
    setHistoricalSession(null);
    setHistoricalLog([]);
    setSessionState(null);
    setPromptInput("");
    setUploadedFile(null);
  }, [resetAgentReview]);

  // Handle Send Prompt
  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend ?? promptInput).trim();
    const fileAttached = uploadedFile;
    if ((!text && !fileAttached) || isRunning) return;

    // Immediately clear input fields
    setPromptInput("");
    setUploadedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    setSubmitting(true);
    setSubmissionError("");

    try {
      const sessionId = activeSessionId || generateSessionId();
      if (!activeSessionId) {
        setActiveSessionId(sessionId);
      }

      let inlineFiles: Array<{ displayName: string; data: string; mimeType: string }> | undefined;
      if (fileAttached) {
        const base64Data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            const res = reader.result as string;
            resolve(res.split(",")[1] || "");
          };
          reader.onerror = reject;
          reader.readAsDataURL(fileAttached);
        });

        const mimeType = fileAttached.name.toLowerCase().endsWith(".zip")
          ? "application/zip"
          : fileAttached.type || "application/zip";

        inlineFiles = [
          {
            displayName: fileAttached.name,
            data: base64Data,
            mimeType,
          },
        ];
      }

      const userDisplayMessage = fileAttached
        ? text
          ? `${text}\n\n📎 Attached: \`${fileAttached.name}\``
          : `📎 Attached: \`${fileAttached.name}\``
        : text;

      await startAgentReview({
        userId,
        sessionId,
        messageText: text || `${fileAttached?.name || "codebase.zip"}`,
        displayText: userDisplayMessage,
        appName,
        inlineFiles,
      });

      saveSession({
        sessionId,
        userRequest: text
          ? fileAttached
            ? `${text} (📎 ${fileAttached.name})`
            : text
          : fileAttached?.name || "Codebase Audit",
        startedAt: Date.now(),
        lastUpdateTime: Date.now(),
        userId,
        appName,
      });
      refreshHistory();
    } catch (err: any) {
      setSubmissionError(err.message || "Failed to communicate with ADK agent.");
    } finally {
      setSubmitting(false);
    }
  };

  // Handle Remediation Approval / Skip
  const handleRemediationDecision = async (approved: boolean) => {
    if (!activeSessionId) return;
    const cmd = approved ? REMEDIATION_APPROVE_CMD : REMEDIATION_SKIP_CMD;
    await startAgentReview({
      userId,
      sessionId: activeSessionId,
      messageText: cmd,
      displayText: approved ? "Approve Remediation Plan" : "Skip Remediation",
      appName,
    });
  };

  const currentSessionState = hookState || sessionState;
  const currentLogs = activeLogs.length > 0 ? activeLogs : historicalLog;
  const elapsedSeconds = Math.floor(elapsedMs / 1000);

  return (
    <div className={`relative flex h-screen w-full overflow-hidden bg-white dark:bg-[#212121] text-black dark:text-[#ECECF1] ${className}`}>
      {/* ─── 1. Left Sidebar ─── */}
      {showSidebar && (
        <GuardianSidebar
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(!sidebarOpen)}
          sessions={recentSessions}
          activeSessionId={activeSessionId ?? undefined}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewChat}
          onDeleteSession={async (sid) => {
            const stored = getSessions().find((s) => s.sessionId === sid);
            const targetUid = stored?.userId || userId;
            const targetApp = stored?.appName || appName;
            removeSession(sid);
            await deleteAdkSession(targetUid, sid, targetApp);
            if (activeSessionId === sid) handleNewChat();
            refreshHistory();
          }}
          userId={userId}
          loading={loadingHistory}
        />
      )}

      {/* ─── 2. Main Agent Workspace Canvas ─── */}
      <div
        className={`flex-1 flex flex-col h-full min-w-0 transition-all duration-300 ${
          showSidebar && sidebarOpen ? "md:ml-[280px]" : showSidebar ? "md:ml-[60px]" : ""
        }`}
      >
        {/* ─── Top Section (Header + Trace Ribbon - Collapsible) ─── */}
        {headerVisible ? (
          <>
            <GuardianHeader
              isSidebarOpen={sidebarOpen}
              onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
              headerVisible={headerVisible}
              onToggleHeader={() => setHeaderVisible(false)}
              activeSessionId={activeSessionId ?? undefined}
              agentTitle={agentTitle}
              availableApps={[appName]}
              activeAppName={appName}
              onToggleInspector={showConsole ? () => setInspectorOpen(!inspectorOpen) : undefined}
              inspectorOpen={inspectorOpen}
              isRunning={isRunning}
            />

            {/* ─── Interactive User Trace Ribbon Bar ─── */}
            {showTraceBar && (activeSessionId !== null || isRunning || currentLogs.length > 0) && (
              <UserTraceBar
                isRunning={isRunning}
                activeAgent={activeAgent}
                activePhase={currentSessionState?.evaluation_grade ? `Grade ${currentSessionState.evaluation_grade} Synthesized` : currentSessionState?.remediation_status}
                elapsedSeconds={elapsedSeconds}
                sessionState={currentSessionState || {}}
                logCount={currentLogs.length}
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

              {showConsole && (
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
              )}
            </div>
          </div>
        )}

        {/* ─── Main Chat Conversation View ─── */}
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-6 space-y-6 max-w-4xl w-full mx-auto">
          {/* Welcome Screen when Empty */}
          {currentLogs.length === 0 && !isRunning && !liveEntry && (
            <div className="flex flex-col items-center justify-center min-h-[50vh] text-center space-y-6 max-w-lg mx-auto py-12 select-none">
              <AgentGuardianLogo size={56} priority />
              <div className="space-y-2">
                <h2 className="text-2xl font-bold tracking-tight text-black dark:text-white">
                  {agentTitle}
                </h2>
                <p className="text-sm text-[#737373] dark:text-[#8E8EA0] leading-relaxed">
                  Autonomous Agent Framework built with Google ADK. Ask questions, audit multi-agent workflows, or execute agent tasks with full real-time telemetry.
                </p>
              </div>

              {/* Starter Quick Actions */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full pt-4 text-left">
                {[
                  {
                    title: "Audit Multi-Agent System",
                    prompt: "Perform a comprehensive security, architecture, and compliance audit on my repository.",
                    icon: Shield,
                  },
                  {
                    title: "Evaluate ADK Pipeline",
                    prompt: "Inspect the multi-agent workflow for race conditions, state mutation loops, and error handling.",
                    icon: Layers,
                  },
                ].map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(item.prompt)}
                    className="p-3.5 rounded-xl border border-black/10 dark:border-white/10 hover:border-[#2525A3]/40 dark:hover:border-[#2525A3]/50 hover:bg-black/[0.02] dark:hover:bg-white/[0.04] transition-all text-left space-y-1 cursor-pointer group"
                  >
                    <div className="flex items-center gap-2">
                      <item.icon className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
                      <span className="text-xs font-semibold text-black dark:text-[#ECECF1] group-hover:text-[#2525A3] dark:group-hover:text-[#A6C3EE] transition-colors">
                        {item.title}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#737373] dark:text-[#8E8EA0] line-clamp-2">
                      {item.prompt}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Conversation Log Rows */}
          {currentLogs.map((entry, idx) => (
            <ChatLogRow
              key={entry.id || idx}
              entry={entry}
              turn={idx + 1}
              onInspectDelta={() => setInspectorOpen(true)}
              onInspectEvent={() => setInspectorOpen(true)}
              onApproveRemediation={() => handleRemediationDecision(true)}
              onSkipRemediation={() => handleRemediationDecision(false)}
            />
          ))}

          {/* Live Streaming Response */}
          {liveEntry && (
            <ChatLogRow
              key="live-streaming-preview"
              entry={liveEntry}
              isStreaming={true}
              onInspectDelta={() => setInspectorOpen(true)}
              onInspectEvent={() => setInspectorOpen(true)}
              onApproveRemediation={() => handleRemediationDecision(true)}
              onSkipRemediation={() => handleRemediationDecision(false)}
            />
          )}

          {/* Error Banner */}
          {(submissionError || hookError) && (
            <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm animate-fade-in">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-semibold">Execution Error</p>
                <p className="text-xs opacity-90">{submissionError || hookError}</p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} className="h-4" />
        </div>

        {/* ─── Bottom Chat Input Area ─── */}
        <div className="p-3 md:p-4 bg-gradient-to-t from-white via-white to-transparent dark:from-[#212121] dark:via-[#212121] dark:to-transparent">
          <div className="max-w-3xl mx-auto space-y-2">
            {/* Attached File Preview Chip */}
            {uploadedFile && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 w-fit text-xs text-black dark:text-[#ECECF1]">
                <Paperclip className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                <span className="font-mono truncate max-w-[200px]">{uploadedFile.name}</span>
                <button
                  onClick={() => setUploadedFile(null)}
                  className="p-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}

            {/* Main Input Box */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="relative flex items-end gap-2 p-2 rounded-2xl bg-black/[0.04] dark:bg-white/[0.06] border border-black/10 dark:border-white/10 focus-within:border-black/30 dark:focus-within:border-white/30 transition-all shadow-sm"
            >
              {/* Attachment Button */}
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => {
                  if (e.target.files?.[0]) setUploadedFile(e.target.files[0]);
                }}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="p-2 rounded-xl text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                title="Attach file"
              >
                <Paperclip className="h-4 w-4" />
              </button>

              {/* Textarea */}
              <textarea
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder={inputPlaceholder || `Message ${agentTitle}...`}
                rows={1}
                className="flex-1 max-h-48 min-h-[24px] resize-none bg-transparent py-1.5 px-2 text-sm text-black dark:text-white placeholder-[#737373] dark:placeholder-[#8E8EA0] outline-none font-sans"
              />

              {/* Submit Button */}
              <button
                type="submit"
                disabled={!promptInput.trim() || isRunning}
                className={`p-2 rounded-xl transition-all cursor-pointer ${
                  promptInput.trim() && !isRunning
                    ? "bg-black dark:bg-white text-white dark:text-black shadow-md hover:opacity-90"
                    : "bg-black/10 dark:bg-white/10 text-black/30 dark:text-white/30 cursor-not-allowed"
                }`}
                title="Send message"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </form>

            <p className="text-[11px] text-center text-[#737373] dark:text-[#8E8EA0] select-none">
              {agentTitle} can make mistakes. Verify critical results and review state.
            </p>
          </div>
        </div>
      </div>

      {/* ─── 3. Telemetry Mission Control Console Drawer ─── */}
      {showConsole && (
        <UserConsoleDrawer
          isOpen={inspectorOpen}
          onClose={() => setInspectorOpen(false)}
          sessionState={currentSessionState || {}}
          selectedEvent={null}
          log={currentLogs}
          isRunning={isRunning}
          userId={userId}
          activeSessionId={activeSessionId}
        />
      )}
    </div>
  );
}
