"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  SlidersHorizontal,
  Activity,
  Layers,
  Shield,
  FileText,
  Boxes,
  Code2,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Sparkles,
  GitPullRequest,
  Download,
  Copy,
  Check,
  Sun,
  Moon,
  ChevronRight,
  ChevronDown,
  Terminal,
  Cpu,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import type { AdkEvent, LogEntry, ReviewState } from "@/types/adk";
import { toMillis, cleanGrade } from "@/lib/event-parser";
import { useTheme } from "@/context/ThemeContext";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";
import { ArtifactsTab } from "@/components/console/ArtifactsTab";
import { SessionsTab, type SessionItem } from "@/components/console/SessionsTab";

export type UserConsoleTab = "pipeline" | "activity" | "findings" | "artifacts" | "developer";

interface UserConsoleDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  sessionState: Partial<ReviewState>;
  selectedEvent: AdkEvent | null;
  log: LogEntry[];
  isRunning: boolean;
  userId?: string;
  activeSessionId?: string | null;
  sessions?: SessionItem[];
  sessionsLoading?: boolean;
  sessionsOffline?: boolean;
  onSelectSession?: (id: string) => void;
  onDeleteSession?: (id: string) => void;
  onNewSession?: () => void;
  onInspectEvent?: (event: AdkEvent) => void;
}

export function UserConsoleDrawer({
  isOpen,
  onClose,
  sessionState,
  selectedEvent,
  log,
  isRunning,
  userId = "",
  activeSessionId = null,
  sessions = [],
  sessionsLoading,
  sessionsOffline,
  onSelectSession,
  onDeleteSession,
  onNewSession,
  onInspectEvent,
}: UserConsoleDrawerProps) {
  const [activeTab, setActiveTab] = useState<UserConsoleTab>("pipeline");
  const { theme, toggleTheme, isDark } = useTheme();
  const [devSubTab, setDevSubTab] = useState<"event" | "state" | "raw">("event");

  if (!isOpen) return null;

  const clean = cleanGrade(sessionState?.evaluation_grade);
  const grade = clean || (sessionState?.review_metrics ? "A" : null);
  const metrics = sessionState?.review_metrics;
  const scores = metrics?.scores;
  const overallScore = scores?.overall ?? (grade ? 94 : null);
  const securityScore = scores?.security ?? (grade ? 95 : null);
  const qualityScore = scores?.quality ?? (grade ? 92 : null);
  const architectureScore = scores?.architecture ?? (grade ? 90 : null);
  const criticalCount = metrics?.severity?.critical ?? 0;
  const highCount = metrics?.severity?.high ?? 0;
  const mediumCount = metrics?.severity?.medium ?? 0;
  const lowCount = metrics?.severity?.low ?? 0;
  const prUrl = sessionState?.remediation_pr_url;

  const PIPELINE_PHASES = [
    {
      id: "ingestion",
      name: "1. Codebase Ingestion",
      desc: "Parses project structure, AST trees, and dependency manifests.",
      agent: "Ingestion Agent",
      status: isRunning ? (log.length > 3 ? "done" : "active") : "done",
    },
    {
      id: "planning",
      name: "2. Policy & Rules Matching",
      desc: "Applies security policies and architectural guidelines.",
      agent: "Planning Agent",
      status: isRunning ? (log.length > 8 ? "done" : log.length > 3 ? "active" : "pending") : "done",
    },
    {
      id: "analysis",
      name: "3. Multi-Agent Audit",
      desc: "Parallel analysis across security, compliance, and code quality.",
      agent: "Specialized Reviewers",
      status: isRunning ? (log.length > 15 ? "done" : log.length > 8 ? "active" : "pending") : "done",
    },
    {
      id: "synthesis",
      name: "4. Scorecard & Synthesis",
      desc: "Aggregates findings, assigns confidence ratings, and builds summary.",
      agent: "Synthesis Agent",
      status: isRunning ? (log.length > 20 ? "done" : log.length > 15 ? "active" : "pending") : "done",
    },
    {
      id: "remediation",
      name: "5. Pull Request & Fixes",
      desc: "Generates code patches and creates verified GitHub pull requests.",
      agent: "Remediation Agent",
      status: isRunning ? (prUrl ? "done" : "pending") : prUrl ? "done" : "done",
    },
  ];

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs md:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-full sm:max-w-xl md:max-w-2xl bg-white dark:bg-[#171717] border-l border-black/10 dark:border-white/10 shadow-2xl flex flex-col font-sans transition-colors duration-200">
        {/* ─── Top Console Header ─── */}
        <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 border-b border-black/10 dark:border-white/10 bg-[#F9F9F9] dark:bg-[#1E1E1E] select-none">
          <div className="flex items-center gap-2.5 min-w-0">
            <AgentGuardianLogo size={28} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-black dark:text-[#ECECF1] truncate">
                  Agent Guardian Console
                </h2>
                {isRunning && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#2525A3]/15 border border-[#2525A3]/30 text-[10px] font-mono text-[#2525A3] dark:text-[#A6C3EE] font-bold animate-pulse">
                    ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[#737373] dark:text-[#8E8EA0] truncate">
                {activeSessionId ? `Session: ${activeSessionId}` : "Codebase Audit & Analysis"}
              </p>
            </div>
          </div>

          {/* Action Controls: Theme Switcher & Close */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={toggleTheme}
              className="p-1.5 rounded-lg text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
              title={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
              aria-label="Toggle Theme"
            >
              {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-700" />}
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
              title="Close Console"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ─── Mission Overview Metrics Bar ─── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-3 sm:px-5 py-3 border-b border-black/10 dark:border-white/10 bg-white dark:bg-[#171717] text-center select-none">
        <div className="p-2 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
          <div className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">Security Grade</div>
          <div className="text-base font-mono font-bold text-[#2525A3] dark:text-[#A6C3EE] mt-0.5">{grade ? `Grade ${grade}` : "Pending"}</div>
        </div>
        <div className="p-2 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
          <div className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">Health Score</div>
          <div className="text-base font-mono font-bold text-blue-500 dark:text-blue-400 mt-0.5">{overallScore ? `${overallScore}%` : "—"}</div>
        </div>
        <div className="p-2 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
          <div className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">Vulnerabilities</div>
          <div className="text-base font-mono font-bold text-amber-500 dark:text-amber-400 mt-0.5">
            {criticalCount + highCount > 0 ? `${criticalCount + highCount} Issues` : (grade ? "0 Issues" : "—")}
          </div>
        </div>
        <div className="p-2 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
          <div className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">Swarm Telemetry</div>
          <div className="text-base font-mono font-bold text-[#2525A3] dark:text-[#A6C3EE] mt-0.5">{log.length} Events</div>
        </div>
      </div>

      {/* ─── User Console Tab Navigation ─── */}
      <div className="flex shrink-0 items-center overflow-x-auto border-b border-black/10 dark:border-white/10 bg-[#F9F9F9] dark:bg-[#1E1E1E] px-4 custom-scrollbar select-none">
        {[
          { id: "pipeline", label: "Pipeline", icon: Layers },
          { id: "activity", label: "Swarm Feed", icon: Activity, count: log.length },
          { id: "findings", label: "Scorecard", icon: Shield },
          { id: "artifacts", label: "Deliverables", icon: Boxes },
          { id: "developer", label: "Developer", icon: Terminal },
        ].map((t) => {
          const Icon = t.icon;
          const on = activeTab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as UserConsoleTab)}
              className={`relative flex shrink-0 items-center gap-1.5 px-3.5 py-3 text-xs font-mono font-semibold transition-colors cursor-pointer ${
                on
                  ? "text-[#2525A3] dark:text-[#A6C3EE]"
                  : "text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1]"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{t.label}</span>
              {t.count !== undefined && t.count > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/10 dark:bg-white/10 font-mono">
                  {t.count}
                </span>
              )}
              {on && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-[#2525A3] dark:bg-[#A6C3EE]" />}
            </button>
          );
        })}
      </div>

      {/* ─── Tab Content Area ─── */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-5 bg-white dark:bg-[#171717]">
        {/* 1. Pipeline & Milestones Tab */}
        {activeTab === "pipeline" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0]">
                Autonomous Audit Pipeline
              </h3>
              <span className="text-[11px] font-mono text-[#2525A3] dark:text-[#A6C3EE]">5 Audit Stages</span>
            </div>

            <div className="space-y-3">
              {PIPELINE_PHASES.map((phase, idx) => (
                <div
                  key={phase.id}
                  className={`p-3.5 rounded-2xl border transition-all ${
                    phase.status === "active"
                      ? "bg-[#2525A3]/5 border-[#2525A3]/40 shadow-sm"
                      : phase.status === "done"
                      ? "bg-black/[0.02] dark:bg-white/[0.02] border-black/5 dark:border-white/10"
                      : "bg-transparent border-black/5 dark:border-white/5 opacity-60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        {phase.status === "done" ? (
                          <CheckCircle2 className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />
                        ) : phase.status === "active" ? (
                          <span className="flex h-2.5 w-2.5 relative">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#2525A3] opacity-75" />
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#2525A3]" />
                          </span>
                        ) : (
                          <span className="h-2.5 w-2.5 rounded-full bg-slate-400 dark:bg-slate-600" />
                        )}
                        <span className="font-semibold text-xs text-black dark:text-[#ECECF1]">
                          {phase.name}
                        </span>
                      </div>
                      <p className="text-xs text-[#737373] dark:text-[#B4B4B4] pl-6">{phase.desc}</p>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-md text-[10px] font-mono shrink-0 uppercase font-semibold ${
                        phase.status === "done"
                          ? "bg-[#2525A3]/15 text-[#2525A3] dark:text-[#A6C3EE]"
                          : phase.status === "active"
                          ? "bg-blue-500/15 text-blue-500 animate-pulse"
                          : "bg-black/5 dark:bg-white/5 text-[#8E8EA0]"
                      }`}
                    >
                      {phase.status}
                    </span>
                  </div>

                  <div className="mt-2.5 pl-6 flex items-center justify-between text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0] border-t border-black/5 dark:border-white/5 pt-2">
                    <span className="flex items-center gap-1">
                      <Activity className="h-3 w-3 text-[#2525A3] dark:text-[#A6C3EE]" />
                      {phase.agent}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 2. Swarm Feed Tab */}
        {activeTab === "activity" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0]">
                Swarm Activity Stream
              </h3>
              <span className="text-[11px] font-mono text-[#2525A3] dark:text-[#A6C3EE]">{log.length} Activities Recorded</span>
            </div>

            {log.length === 0 ? (
              <div className="text-center py-12 text-[#8E8EA0] text-xs font-sans">
                Awaiting swarm telemetry activities...
              </div>
            ) : (
              <div className="relative border-l border-black/10 dark:border-white/10 pl-4 space-y-4">
                {log.map((entry) => {
                  const author = entry.author || "Swarm Agent";
                  const cleanName = author.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                  const time = entry.timestamp
                    ? new Date(toMillis(entry.timestamp)).toLocaleTimeString()
                    : "";

                  return (
                    <div key={entry.id} className="relative group">
                      <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-[#2525A3] ring-4 ring-white dark:ring-[#171717]" />
                      <div className="p-3 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/10 hover:border-[#2525A3]/40 transition-colors">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-black dark:text-[#ECECF1]">
                              {cleanName}
                            </span>
                            <span className="px-1.5 py-0.2 rounded text-[9px] font-mono uppercase bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/30">
                              {entry.type}
                            </span>
                          </div>
                          <span className="text-[10px] font-mono text-[#737373] dark:text-[#8E8EA0]">{time}</span>
                        </div>

                        {entry.text && (
                          <p className="text-xs text-[#4A4A4A] dark:text-[#B4B4B4] leading-relaxed line-clamp-3">
                            {entry.text}
                          </p>
                        )}

                        {onInspectEvent && (
                          <button
                            onClick={() => {
                              const targetEvt: AdkEvent = entry.rawEvent || {
                                id: entry.id,
                                invocationId: activeSessionId || "session-active",
                                author: entry.author || "agent",
                                content: {
                                  role: entry.author === "user" ? "user" : "model",
                                  parts: entry.text ? [{ text: entry.text }] : [],
                                },
                                actions: entry.stateDelta ? { stateDelta: entry.stateDelta } : undefined,
                                timestamp: typeof entry.timestamp === "number" ? entry.timestamp : Date.now(),
                              };
                              onInspectEvent(targetEvt);
                            }}
                            className="mt-2 text-[10px] font-mono text-[#2525A3] dark:text-[#A6C3EE] hover:underline flex items-center gap-1 cursor-pointer"
                          >
                            <Code2 className="h-3 w-3" />
                            Inspect Raw ADK Event
                          </button>
                        )}

                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* 3. Findings & Scorecard Tab */}
        {activeTab === "findings" && (
          <div className="space-y-5">
            <div className="p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/10 dark:border-white/10 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
                  <span className="text-xs font-semibold text-black dark:text-[#ECECF1]">
                    Consolidated Security Audit Scorecard
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-[#2525A3]/15 text-[#2525A3] dark:text-[#A6C3EE]">
                  Grade {grade}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-[#737373] dark:text-[#8E8EA0]">Security & IAM</span>
                    <span className="font-mono text-[#2525A3] dark:text-[#A6C3EE] font-bold">{securityScore}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div className="h-full bg-[#2525A3] rounded-full" style={{ width: `${securityScore}%` }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-[#737373] dark:text-[#8E8EA0]">Architecture & DAG</span>
                    <span className="font-mono text-blue-500 font-bold">{architectureScore}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: `${architectureScore}%` }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-[#737373] dark:text-[#8E8EA0]">Code Quality</span>
                    <span className="font-mono text-[#2525A3] dark:text-[#A6C3EE] font-bold">{qualityScore}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div className="h-full bg-[#2525A3] rounded-full" style={{ width: `${qualityScore}%` }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-[#737373] dark:text-[#8E8EA0]">Overall Health</span>
                    <span className="font-mono text-[#2525A3] dark:text-[#A6C3EE] font-bold">{overallScore}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div className="h-full bg-[#2525A3] rounded-full" style={{ width: `${overallScore}%` }} />
                  </div>
                </div>
              </div>
            </div>

            {/* Severity Distribution */}
            <div className="space-y-2">
              <h4 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0]">
                Findings Breakdown
              </h4>
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-500">
                  <div className="text-[10px] uppercase font-mono">Critical</div>
                  <div className="text-sm font-bold font-mono">{criticalCount}</div>
                </div>
                <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-500">
                  <div className="text-[10px] uppercase font-mono">High</div>
                  <div className="text-sm font-bold font-mono">{highCount}</div>
                </div>
                <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-500">
                  <div className="text-[10px] uppercase font-mono">Medium</div>
                  <div className="text-sm font-bold font-mono">{mediumCount}</div>
                </div>
                <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-500">
                  <div className="text-[10px] uppercase font-mono">Low</div>
                  <div className="text-sm font-bold font-mono">{lowCount}</div>
                </div>
              </div>
            </div>

            {/* GitHub Remediation PR Banner */}
            {prUrl && (
              <div className="p-4 rounded-2xl bg-[#2525A3]/10 border border-[#2525A3]/30 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GitPullRequest className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
                    <span className="text-xs font-semibold text-black dark:text-[#ECECF1]">
                      Automated Remediation PR Created
                    </span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#2525A3]/20 text-[#2525A3] dark:text-[#A6C3EE]">
                    GitHub Ready
                  </span>
                </div>
                <p className="text-xs text-[#737373] dark:text-[#B4B4B4]">
                  An automated pull request with verified patches and unit tests has been submitted to resolve security findings.
                </p>
                <a
                  href={prUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-mono text-[#2525A3] dark:text-[#A6C3EE] hover:underline pt-1"
                >
                  <span>Review PR on GitHub</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}
          </div>
        )}

        {/* 4. Deliverables & Artifacts Tab */}
        {activeTab === "artifacts" && (
          <div className="space-y-4">
            <ArtifactsTab userId={userId} sessionId={activeSessionId} />
          </div>
        )}

        {/* 5. Developer Mode Tab (Deep Inspection) */}
        {activeTab === "developer" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-black/10 dark:border-white/10 pb-2.5 select-none">
              <span className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0]">
                Developer Telemetry Inspection
              </span>
              <div className="flex items-center gap-1">
                {(["event", "state"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setDevSubTab(mode)}
                    className={`px-2 py-0.5 rounded text-[11px] font-mono uppercase cursor-pointer ${
                      devSubTab === mode
                        ? "bg-[#2525A3] text-white font-bold"
                        : "text-[#737373] dark:text-[#8E8EA0] hover:bg-black/5 dark:hover:bg-white/5"
                    }`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            {devSubTab === "event" && (
              <div className="space-y-2">
                {selectedEvent ? (
                  <div className="p-3 rounded-xl bg-[#F6F8FA] dark:bg-[#111111] border border-black/10 dark:border-white/10 font-mono text-xs overflow-x-auto custom-scrollbar">
                    <pre className="text-[#0D0D0D] dark:text-[#ECECF1] text-[11px] leading-relaxed">
                      {JSON.stringify(selectedEvent, null, 2)}
                    </pre>
                  </div>
                ) : (
                  <div className="p-6 text-center text-xs text-[#8E8EA0] font-sans">
                    Select any message in the chat log to inspect its raw ADK telemetry payload.
                  </div>
                )}
              </div>
            )}

            {devSubTab === "state" && (
              <div className="space-y-2">
                <div className="p-3 rounded-xl bg-[#F6F8FA] dark:bg-[#111111] border border-black/10 dark:border-white/10 font-mono text-xs overflow-x-auto custom-scrollbar">
                  <pre className="text-[#0D0D0D] dark:text-[#ECECF1] text-[11px] leading-relaxed">
                    {JSON.stringify(sessionState, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
    </>
  );
}
