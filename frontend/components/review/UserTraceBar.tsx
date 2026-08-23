"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  Activity,
  CheckCircle2,
  SlidersHorizontal,
  GitPullRequest,
  Clock,
  MessageSquare,
} from "lucide-react";
import type { ReviewState } from "@/types/adk";

interface UserTraceBarProps {
  chatTitle?: string;
  isRunning: boolean;
  activeAgent?: string | null;
  activePhase?: string | null;
  elapsedSeconds?: number;
  sessionState?: Partial<ReviewState>;
  logCount?: number;
  onOpenConsole: () => void;
  onOpenArtifacts?: () => void;
}

export function UserTraceBar({
  chatTitle,
  isRunning,
  activeAgent,
  activePhase,
  elapsedSeconds = 0,
  sessionState,
  logCount = 0,
  onOpenConsole,
  onOpenArtifacts,
}: UserTraceBarProps) {
  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const s = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const prUrl = sessionState?.remediation_pr_url;

  // Pretty phase label
  const phaseLabel = activePhase
    ? activePhase.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : isRunning
    ? "Reviewing & Analyzing"
    : "Audit Complete";

  const cleanAgent = activeAgent
    ? activeAgent.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : isRunning
    ? "Multi-Agent Swarm"
    : "Agent Guardian";

  const displayTitle = chatTitle && chatTitle.trim() ? chatTitle.trim() : "Agent Guardian Audit";

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full bg-[#F7F7F8] dark:bg-[#252525] border-b border-black/10 dark:border-white/10 px-3 md:px-5 py-2 flex flex-wrap items-center justify-between gap-3 text-xs select-none transition-colors duration-200"
    >
      {/* Left: Chat Title / Subject + Live Status */}
      <div className="flex items-center gap-2 sm:gap-2.5 flex-1 min-w-0">
        {/* Chat / Status Icon */}
        <div className="flex items-center gap-1.5 shrink-0">
          {isRunning ? (
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#2525A3] opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#2525A3]" />
            </span>
          ) : (
            <CheckCircle2 className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />
          )}
        </div>

        {/* Chat Name */}
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className="font-semibold text-xs sm:text-sm text-black dark:text-[#ECECF1] truncate"
            title={displayTitle}
          >
            {displayTitle}
          </span>
        </div>

        <span className="text-[#737373] dark:text-[#8E8EA0] hidden sm:inline">•</span>

        {/* Status / Active Agent Badge */}
        {isRunning ? (
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10 text-[11px] text-[#4A4A4A] dark:text-[#B4B4B4] truncate">
            <Activity className="h-3 w-3 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />
            <span className="truncate">{cleanAgent}</span>
          </div>
        ) : (
          <span className="hidden sm:inline text-[11px] text-[#737373] dark:text-[#8E8EA0]">
            {phaseLabel}
          </span>
        )}

        {/* Elapsed Timer */}
        {isRunning && (
          <div className="flex items-center gap-1 text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0]">
            <Clock className="h-3 w-3" />
            <span>{formatTime(elapsedSeconds)}</span>
          </div>
        )}
      </div>

      {/* Right: PR Chip + User Console Button */}
      <div className="flex items-center gap-2 shrink-0 ml-auto">
        {/* Remediation PR Chip */}
        {prUrl && (
          <a
            href={prUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden md:flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#2525A3]/10 border border-[#2525A3]/30 text-[11px] font-mono text-[#2525A3] dark:text-[#A6C3EE] hover:bg-[#2525A3]/20 transition-colors"
          >
            <GitPullRequest className="h-3 w-3" />
            <span>1-Click PR</span>
          </a>
        )}

        {/* Main User Console Launch Button */}
        <button
          onClick={onOpenConsole}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg border border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 text-black dark:text-[#ECECF1] text-xs font-medium transition-colors cursor-pointer"
          title="Open Mission Control Console"
        >
          <SlidersHorizontal className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
          <span>Console</span>
        </button>
      </div>
    </motion.div>
  );
}
