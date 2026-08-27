"use client";

import React, { useState, useMemo } from "react";
import {
  PanelLeftClose,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  Check,
  X,
  Activity,
  ChevronDown,
  PanelLeft,
  SquarePen,
  LogOut,
  Sun,
  Moon,
} from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";
import { logoutAndClearWorkspace, formatChatTitle } from "@/lib/session";

export interface EnrichedSessionItem {
  sessionId: string;
  userRequest?: string;
  startedAt?: number;
  lastUpdateTime?: number;
  grade?: "A" | "B" | "C" | "D" | "F" | string;
  securityScore?: number;
  criticalIssues?: number;
  repoName?: string;
  adkAlive?: boolean;
  status?: string;
}

export interface GuardianSidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  sessions: EnrichedSessionItem[];
  activeSessionId?: string;
  userId: string;
  loading?: boolean;
  offline?: boolean;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onNewSession: () => void;
  onOpenTelemetry?: () => void;
  onOpenDiagnostics?: () => void;
  onOpenShare?: (sessionId: string) => void;
  onOpenSearch?: () => void;
  onLogout?: () => void;
  onSaveUserId?: (newUserId: string) => void;
  editableUser?: boolean;
}

function parseRepoLabel(userRequest?: string, repoName?: string, sessionId?: string): string {
  return formatChatTitle(userRequest, repoName, sessionId);
}

export function GuardianSidebar({
  isOpen,
  onToggle,
  sessions,
  activeSessionId,
  userId,
  loading = false,
  offline = false,
  onSelectSession,
  onDeleteSession,
  onNewSession,
  onOpenTelemetry,
  onOpenDiagnostics,
  onOpenShare,
  onOpenSearch,
  onLogout,
  onSaveUserId,
  editableUser = true,
}: GuardianSidebarProps) {
  const [search, setSearch] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [draftUserId, setDraftUserId] = useState(userId);
  const [userIdError, setUserIdError] = useState("");
  const { theme, toggleTheme, isDark } = useTheme();

  // Clean search filter: matches by session ID, repo name, and user request prompt, sorted by timestamp descending
  const filteredSessions = useMemo(() => {
    let list = sessions;
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      list = sessions.filter((s) => {
        const sidMatch = s.sessionId.toLowerCase().includes(q);
        const reqMatch = s.userRequest ? s.userRequest.toLowerCase().includes(q) : false;
        const repoMatch = s.repoName ? s.repoName.toLowerCase().includes(q) : false;
        const titleMatch = parseRepoLabel(s.userRequest, s.repoName, s.sessionId).toLowerCase().includes(q);
        return sidMatch || reqMatch || repoMatch || titleMatch;
      });
    }

    return [...list].sort((a, b) => {
      const timeA = a.lastUpdateTime || a.startedAt || 0;
      const timeB = b.lastUpdateTime || b.startedAt || 0;
      return timeB - timeA;
    });
  }, [sessions, search]);

  // Group sessions chronologically (Today, Yesterday, Previous 7 Days, Previous 30 Days, Older)
  const groupedSessions = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
    const startOfPast7Days = startOfToday - 7 * 24 * 60 * 60 * 1000;
    const startOfPast30Days = startOfToday - 30 * 24 * 60 * 60 * 1000;

    const today: EnrichedSessionItem[] = [];
    const yesterday: EnrichedSessionItem[] = [];
    const pastWeek: EnrichedSessionItem[] = [];
    const pastMonth: EnrichedSessionItem[] = [];
    const older: EnrichedSessionItem[] = [];

    filteredSessions.forEach((s) => {
      const d = s.lastUpdateTime || s.startedAt || Date.now();
      if (d >= startOfToday) {
        today.push(s);
      } else if (d >= startOfYesterday) {
        yesterday.push(s);
      } else if (d >= startOfPast7Days) {
        pastWeek.push(s);
      } else if (d >= startOfPast30Days) {
        pastMonth.push(s);
      } else {
        older.push(s);
      }
    });

    return { today, yesterday, pastWeek, pastMonth, older };
  }, [filteredSessions]);

  const handleSaveUser = () => {
    const trimmed = draftUserId.trim();
    if (!trimmed) {
      setUserIdError("Callsign cannot be empty");
      return;
    }
    if (trimmed.length > 32) {
      setUserIdError("Max 32 characters");
      return;
    }
    setUserIdError("");
    onSaveUserId?.(trimmed);
    setUserMenuOpen(false);
  };

  const renderGradeBadge = (session: EnrichedSessionItem) => {
    if (session.status === "ACTIVE") {
      return (
        <span className="flex h-2 w-2 relative" title="Live Running Audit">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#2525A3] opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-[#2525A3]" />
        </span>
      );
    }
    return null;
  };

  const handleSelectSessionMobile = (id: string) => {
    onSelectSession(id);
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      onToggle();
    }
  };

  const handleNewSessionMobile = () => {
    onNewSession();
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      onToggle();
    }
  };

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-xs md:hidden transition-opacity"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col overflow-hidden bg-[#F9F9F9] dark:bg-[#171717] transition-all duration-300 select-none ${
          isOpen
            ? "w-[280px] max-w-[85vw] border-r border-black/10 dark:border-white/10 shadow-2xl md:shadow-none translate-x-0"
            : "w-0 -translate-x-full border-r-0 pointer-events-none opacity-0 md:opacity-100 md:pointer-events-auto md:translate-x-0 md:w-[60px] md:border-r md:border-black/10 dark:md:border-white/10"
        }`}
        aria-label="Sidebar Navigation"
      >
        {/* Expanded Sidebar View */}
        {isOpen ? (
          <div className="flex flex-col h-full w-[280px] max-w-[85vw] overflow-hidden">
            {/* Top Header Row */}
            <div className="flex items-center justify-between px-3 py-3 border-b border-black/5 dark:border-white/5">
              <div className="flex items-center gap-2">
                <AgentGuardianLogo size={32} />
                <div className="flex flex-col">
                  <span className="text-xs font-semibold text-black dark:text-[#ECECF1] tracking-tight">
                    Agent Guardian
                  </span>
                  <span className="text-[10px] text-[#737373] dark:text-[#8E8EA0] font-mono">
                    Code Auditor
                  </span>
                </div>
              </div>

              <button
                onClick={onToggle}
                className="p-1.5 rounded-lg text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                title="Close sidebar"
                aria-label="Close sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </div>

            {/* New Chat Button Row */}
            <div className="p-3">
              <button
                onClick={handleNewSessionMobile}
                className="flex items-center justify-between w-full px-3 py-2.5 rounded-xl border border-black/10 dark:border-white/10 hover:border-[#2525A3]/40 dark:hover:border-[#2525A3]/50 bg-white dark:bg-white/[0.04] hover:bg-black/5 dark:hover:bg-white/[0.08] text-black dark:text-[#ECECF1] text-xs font-medium transition-all group shadow-sm cursor-pointer"
              >
                <div className="flex items-center gap-2.5">
                  <div className="flex h-5 w-5 items-center justify-center rounded-full bg-black/10 dark:bg-white/10 group-hover:bg-[#2525A3] group-hover:text-white transition-colors text-black dark:text-[#ECECF1]">
                    <Plus className="h-3.5 w-3.5" />
                  </div>
                  <span>New audit</span>
                </div>
                <SquarePen className="h-3.5 w-3.5 text-[#737373] dark:text-[#8E8EA0] group-hover:text-black dark:group-hover:text-[#ECECF1]" />
              </button>
            </div>

            {/* Search bar */}
            <div className="px-3 pb-2">
              <div className="relative flex items-center">
                <Search className="absolute left-2.5 h-3.5 w-3.5 text-[#737373] dark:text-[#8E8EA0]" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search audits..."
                  className="w-full pl-8 pr-12 py-1.5 rounded-lg bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 text-xs text-black dark:text-[#ECECF1] placeholder-[#737373] dark:placeholder-[#8E8EA0] focus:outline-none focus:border-[#2525A3]/50 focus:bg-white dark:focus:bg-white/[0.06] transition-all"
                />
                <div className="absolute right-1.5 flex items-center gap-1">
                  {search ? (
                    <button
                      onClick={() => setSearch("")}
                      className="p-1 rounded text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] cursor-pointer"
                      title="Clear search"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  ) : onOpenSearch ? (
                    <button
                      onClick={onOpenSearch}
                      className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium text-[#737373] dark:text-[#8E8EA0] bg-black/5 dark:bg-white/10 hover:text-black dark:hover:text-white transition-colors cursor-pointer"
                      title="Search audits (⌘K)"
                    >
                      ⌘K
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            {/* Quick Action Navigation Links */}
            <div className="px-3 py-1 space-y-0.5 border-b border-black/5 dark:border-white/5">
              {onOpenTelemetry && (
                <button
                  onClick={onOpenTelemetry}
                  className="flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-lg text-xs text-[#4A4A4A] dark:text-[#B4B4B4] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/[0.04] transition-colors cursor-pointer"
                >
                  <Activity className="h-3.5 w-3.5 text-blue-500 dark:text-blue-400" />
                  <span className="font-medium">Console & Telemetry</span>
                </button>
              )}
            </div>

            {/* Chronological Chat & Audit History */}
            <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2 space-y-3 custom-scrollbar">
              {loading && (
                <div className="px-3 py-4 text-center text-xs text-[#737373] dark:text-[#8E8EA0]">
                  Loading audits...
                </div>
              )}

              {!loading && filteredSessions.length === 0 && (
                <div className="px-3 py-6 text-center text-xs text-[#737373] dark:text-[#8E8EA0]">
                  {search ? "No matching audits found" : "No previous audits yet"}
                </div>
              )}

              {/* Today Group */}
              {groupedSessions.today.length > 0 && (
                <div className="space-y-0.5">
                  <div className="px-2.5 py-1 text-[11px] font-semibold text-[#737373] dark:text-[#8E8EA0] tracking-tight">
                    Today
                  </div>
                  {groupedSessions.today.map((s) =>
                    renderSessionItem(
                      s,
                      activeSessionId,
                      confirmDeleteId,
                      handleSelectSessionMobile,
                      setConfirmDeleteId,
                      onDeleteSession,
                      renderGradeBadge
                    )
                  )}
                </div>
              )}

              {/* Yesterday Group */}
              {groupedSessions.yesterday.length > 0 && (
                <div className="space-y-0.5">
                  <div className="px-2.5 py-1 text-[11px] font-semibold text-[#737373] dark:text-[#8E8EA0] tracking-tight">
                    Yesterday
                  </div>
                  {groupedSessions.yesterday.map((s) =>
                    renderSessionItem(
                      s,
                      activeSessionId,
                      confirmDeleteId,
                      handleSelectSessionMobile,
                      setConfirmDeleteId,
                      onDeleteSession,
                      renderGradeBadge
                    )
                  )}
                </div>
              )}

              {/* Previous 7 Days */}
              {groupedSessions.pastWeek.length > 0 && (
                <div className="space-y-0.5">
                  <div className="px-2.5 py-1 text-[11px] font-semibold text-[#737373] dark:text-[#8E8EA0] tracking-tight">
                    Previous 7 Days
                  </div>
                  {groupedSessions.pastWeek.map((s) =>
                    renderSessionItem(
                      s,
                      activeSessionId,
                      confirmDeleteId,
                      handleSelectSessionMobile,
                      setConfirmDeleteId,
                      onDeleteSession,
                      renderGradeBadge
                    )
                  )}
                </div>
              )}

              {/* Previous 30 Days */}
              {groupedSessions.pastMonth.length > 0 && (
                <div className="space-y-0.5">
                  <div className="px-2.5 py-1 text-[11px] font-semibold text-[#737373] dark:text-[#8E8EA0] tracking-tight">
                    Previous 30 Days
                  </div>
                  {groupedSessions.pastMonth.map((s) =>
                    renderSessionItem(
                      s,
                      activeSessionId,
                      confirmDeleteId,
                      handleSelectSessionMobile,
                      setConfirmDeleteId,
                      onDeleteSession,
                      renderGradeBadge
                    )
                  )}
                </div>
              )}

              {/* Older */}
              {groupedSessions.older.length > 0 && (
                <div className="space-y-0.5">
                  <div className="px-2.5 py-1 text-[11px] font-semibold text-[#737373] dark:text-[#8E8EA0] tracking-tight">
                    Older
                  </div>
                  {groupedSessions.older.map((s) =>
                    renderSessionItem(
                      s,
                      activeSessionId,
                      confirmDeleteId,
                      handleSelectSessionMobile,
                      setConfirmDeleteId,
                      onDeleteSession,
                      renderGradeBadge
                    )
                  )}
                </div>
              )}
            </div>

            {/* User Profile Footer */}
            <div className="p-2 border-t border-black/5 dark:border-white/5 relative">
              <button
                onClick={() => {
                  setDraftUserId(userId);
                  setUserMenuOpen(!userMenuOpen);
                }}
                className="flex items-center justify-between w-full p-2 rounded-xl hover:bg-black/5 dark:hover:bg-white/5 transition-colors group cursor-pointer"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div
                    suppressHydrationWarning
                    className="flex h-7 w-7 items-center justify-center rounded-full bg-[#2525A3]/20 text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/40 text-xs font-bold shrink-0"
                  >
                    {userId ? userId.slice(0, 2).toUpperCase() : "AG"}
                  </div>
                  <div className="flex flex-col text-left min-w-0">
                    <span suppressHydrationWarning className="text-xs font-semibold text-black dark:text-[#ECECF1] truncate">
                      {userId || "Operator"}
                    </span>
                    <span className="text-[10px] text-[#737373] dark:text-[#8E8EA0] truncate">
                      {offline ? "Offline Storage" : "ADK 2.0 Connected"}
                    </span>
                  </div>
                </div>
                <ChevronDown className="h-3.5 w-3.5 text-[#737373] dark:text-[#8E8EA0] group-hover:text-black dark:group-hover:text-white transition-transform" />
              </button>

              {/* Operator Menu Popover */}
              {userMenuOpen && (
                <div className="absolute bottom-full left-2 right-2 mb-2 p-3 rounded-2xl bg-white dark:bg-[#212121] border border-black/10 dark:border-white/10 shadow-2xl space-y-3 z-50 animate-scale-in">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-black dark:text-white">
                      Operator Account
                    </span>
                    <button
                      onClick={() => setUserMenuOpen(false)}
                      className="text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white cursor-pointer"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>

                  {editableUser && (
                    <div className="space-y-2">
                      <label className="text-[11px] text-[#737373] dark:text-[#8E8EA0] font-mono">
                        User ID / Email
                      </label>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          value={draftUserId}
                          onChange={(e) => setDraftUserId(e.target.value)}
                          className="flex-1 px-2.5 py-1.5 rounded-lg bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 text-xs text-black dark:text-white focus:outline-none focus:border-[#2525A3]"
                        />
                        <button
                          onClick={handleSaveUser}
                          className="px-2.5 py-1.5 rounded-lg bg-[#2525A3] hover:bg-[#1E1E88] text-white text-xs font-semibold transition-colors cursor-pointer"
                        >
                          Save
                        </button>
                      </div>
                      {userIdError && (
                        <span className="text-[10px] text-red-400">{userIdError}</span>
                      )}
                    </div>
                  )}

                  {/* Theme Switcher in Popover */}
                  <div className="pt-2 border-t border-black/5 dark:border-white/5 flex items-center justify-between">
                    <span className="text-xs text-[#4A4A4A] dark:text-[#B4B4B4]">Appearance</span>
                    <button
                      onClick={toggleTheme}
                      className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-medium text-black dark:text-white transition-colors cursor-pointer"
                    >
                      {isDark ? (
                        <>
                          <Sun className="h-3.5 w-3.5 text-amber-400" />
                          <span>Light Mode</span>
                        </>
                      ) : (
                        <>
                          <Moon className="h-3.5 w-3.5 text-slate-700" />
                          <span>Dark Mode</span>
                        </>
                      )}
                    </button>
                  </div>

                  <div className="pt-1 border-t border-black/5 dark:border-white/5 space-y-1">
                    {onOpenDiagnostics && (
                      <button
                        onClick={() => {
                          setUserMenuOpen(false);
                          onOpenDiagnostics();
                        }}
                        className="flex items-center gap-2 w-full px-2 py-1.5 rounded-lg text-xs text-black dark:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left cursor-pointer"
                      >
                        <SlidersHorizontal className="h-3.5 w-3.5 text-[#737373] dark:text-[#8E8EA0]" />
                        <span>Diagnostics & Health</span>
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setUserMenuOpen(false);
                        if (onLogout) {
                          onLogout();
                        } else {
                          logoutAndClearWorkspace();
                          window.location.reload();
                        }
                      }}
                      className="flex items-center gap-2 w-full px-2 py-1.5 rounded-lg text-xs text-red-500 hover:bg-red-500/10 transition-colors text-left cursor-pointer font-medium"
                      title="Log out and switch workspace (clears local storage)"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                      <span>Log Out / Switch Workspace</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Collapsed Sidebar Rail */
          <div className="hidden md:flex flex-col items-center justify-between h-full w-[60px] py-3 overflow-hidden">
            <div className="flex flex-col items-center gap-3">
              <button
                onClick={onToggle}
                className="p-2 rounded-lg text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                title="Open sidebar"
                aria-label="Open sidebar"
              >
                <PanelLeft className="h-5 w-5" />
              </button>

              <button
                onClick={onNewSession}
                className="flex h-9 w-9 items-center justify-center rounded-xl bg-black/5 dark:bg-white/[0.06] hover:bg-[#2525A3] text-black dark:text-[#ECECF1] hover:text-white transition-all shadow-sm cursor-pointer"
                title="New audit"
                aria-label="New audit"
              >
                <Plus className="h-4 w-4" />
              </button>

              {onOpenSearch && (
                <button
                  onClick={onOpenSearch}
                  className="flex h-9 w-9 items-center justify-center rounded-xl hover:bg-black/5 dark:hover:bg-white/5 text-[#737373] dark:text-[#8E8EA0] hover:text-[#2525A3] dark:hover:text-[#A6C3EE] transition-all cursor-pointer"
                  title="Search audits (⌘K)"
                  aria-label="Search audits"
                >
                  <Search className="h-4 w-4" />
                </button>
              )}

              {(onOpenTelemetry || onOpenDiagnostics) && (
                <button
                  onClick={onOpenTelemetry || onOpenDiagnostics}
                  className="flex h-9 w-9 items-center justify-center rounded-xl hover:bg-black/5 dark:hover:bg-white/5 text-[#737373] dark:text-[#8E8EA0] hover:text-blue-500 dark:hover:text-blue-400 transition-all cursor-pointer"
                  title="Swarm Telemetry"
                  aria-label="Swarm Telemetry"
                >
                  <Activity className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Bottom user avatar */}
            <div className="flex flex-col items-center gap-2">
              <button
                onClick={toggleTheme}
                className="p-2 rounded-lg text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                title={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
              >
                {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-700" />}
              </button>
              <button
                onClick={() => {
                  if (onLogout) {
                    onLogout();
                  } else {
                    logoutAndClearWorkspace();
                    window.location.reload();
                  }
                }}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[#2525A3]/20 text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/40 hover:border-red-500 hover:bg-red-500/20 hover:text-red-500 text-xs font-bold transition-all cursor-pointer"
                title={`Logged in as ${userId || "Operator"}. Click to Log Out / Switch Workspace.`}
              >
                {userId.slice(0, 2).toUpperCase() || "AG"}
              </button>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}

function renderSessionItem(
  session: EnrichedSessionItem,
  activeSessionId: string | undefined,
  confirmDeleteId: string | null,
  onSelectSession: (id: string) => void,
  setConfirmDeleteId: (id: string | null) => void,
  onDeleteSession: (id: string) => void,
  renderGradeBadge: (s: EnrichedSessionItem) => React.ReactNode
) {
  const isSelected = activeSessionId === session.sessionId;
  const isConfirming = confirmDeleteId === session.sessionId;
  const label = parseRepoLabel(session.userRequest, session.repoName, session.sessionId);
  const timestamp = session.lastUpdateTime || session.startedAt;
  const timeFormatted = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";
  const tooltip = timeFormatted ? `${label} • ${timeFormatted}` : label;

  if (isConfirming) {
    return (
      <div
        key={session.sessionId}
        className="flex items-center justify-between p-2 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-500 animate-fade-in"
      >
        <span className="text-[11px] truncate">Delete audit?</span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onDeleteSession(session.sessionId)}
            className="p-1 rounded hover:bg-red-500/30 text-red-500 hover:text-red-600 cursor-pointer"
            title="Confirm Delete"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setConfirmDeleteId(null)}
            className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white cursor-pointer"
            title="Cancel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      key={session.sessionId}
      onClick={() => onSelectSession(session.sessionId)}
      title={tooltip}
      className={`group relative flex items-center justify-between px-2.5 py-2 rounded-xl text-xs transition-colors cursor-pointer ${
        isSelected
          ? "bg-black/5 dark:bg-[#212121] text-black dark:text-[#ECECF1] font-semibold"
          : "text-[#737373] dark:text-[#8E8EA0] hover:bg-black/5 dark:hover:bg-white/[0.04] hover:text-black dark:hover:text-[#ECECF1]"
      }`}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1 pr-1">
        <span className="truncate">{label}</span>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        {renderGradeBadge(session)}

        {/* Action icons shown on hover */}
        <div className="hidden group-hover:flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setConfirmDeleteId(session.sessionId);
            }}
            className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10 text-[#737373] dark:text-[#8E8EA0] hover:text-red-500 transition-colors cursor-pointer"
            title="Delete audit"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
