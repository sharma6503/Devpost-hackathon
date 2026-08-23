"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Search,
  X,
  Clock,
  GitBranch,
  FolderArchive,
  MessageSquare,
  ArrowRight,
  Sparkles,
  Command,
  CornerDownLeft,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { EnrichedSessionItem } from "@/components/guardian/GuardianSidebar";
import { formatChatTitle } from "@/lib/session";


export interface AuditSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessions: EnrichedSessionItem[];
  activeSessionId?: string;
  onSelectSession: (sessionId: string) => void;
  onNewSession?: () => void;
}

function formatTimestamp(timestamp?: number): string {
  if (!timestamp) return "Recent";
  const now = Date.now();
  const diff = now - timestamp;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function AuditSearchModal({
  isOpen,
  onClose,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
}: AuditSearchModalProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Clean filtered session list based on query, sorted by timestamp descending
  const filteredSessions = useMemo(() => {
    let list = sessions;
    const q = query.trim().toLowerCase();
    if (q) {
      list = sessions.filter((s) => {
        const title = formatChatTitle(s.userRequest, s.repoName, s.sessionId).toLowerCase();
        const sidMatch = s.sessionId.toLowerCase().includes(q);
        const reqMatch = s.userRequest ? s.userRequest.toLowerCase().includes(q) : false;
        const repoMatch = s.repoName ? s.repoName.toLowerCase().includes(q) : false;
        const titleMatch = title.includes(q);

        return sidMatch || reqMatch || repoMatch || titleMatch;
      });
    }

    return [...list].sort((a, b) => {
      const timeA = a.lastUpdateTime || a.startedAt || 0;
      const timeB = b.lastUpdateTime || b.startedAt || 0;
      return timeB - timeA;
    });
  }, [sessions, query]);


  // Auto-focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Global keydown listeners for keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1 < filteredSessions.length ? prev + 1 : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : Math.max(0, filteredSessions.length - 1)));
      } else if (e.key === "Enter" && filteredSessions.length > 0) {
        e.preventDefault();
        const selected = filteredSessions[selectedIndex];
        if (selected) {
          onSelectSession(selected.sessionId);
          onClose();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, selectedIndex, filteredSessions, onClose, onSelectSession]);

  // Scroll active item into view
  useEffect(() => {
    if (listRef.current) {
      const activeEl = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      if (activeEl) {
        activeEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 sm:pt-24 p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
        {/* Backdrop click to close */}
        <div className="fixed inset-0" onClick={onClose} />

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: -12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -12 }}
          transition={{ duration: 0.16 }}
          className="relative w-full max-w-2xl bg-white dark:bg-[#212121] rounded-2xl shadow-2xl border border-black/10 dark:border-white/10 overflow-hidden flex flex-col max-h-[80vh] z-10"
        >
          {/* Top Search Input Box */}
          <div className="flex items-center gap-3 px-4 py-3.5 border-b border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.02]">
            <Search className="h-5 w-5 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              placeholder="Search audits by repository, session ID, or query..."
              className="flex-1 bg-transparent text-sm sm:text-base text-black dark:text-white placeholder:text-[#737373] dark:placeholder:text-[#8E8EA0] outline-none font-sans"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="p-1 rounded-md text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors cursor-pointer"
                title="Clear query"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            <kbd className="hidden sm:inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-mono font-medium text-[#737373] dark:text-[#8E8EA0] bg-black/5 dark:bg-white/10 border border-black/10 dark:border-white/10">
              ESC
            </kbd>
          </div>

          {/* Results List */}
          <div ref={listRef} className="flex-1 overflow-y-auto p-2 space-y-1 divide-y divide-black/5 dark:divide-white/5">
            {filteredSessions.length === 0 ? (
              <div className="py-12 text-center text-sm text-[#737373] dark:text-[#8E8EA0] space-y-3">
                <Search className="h-8 w-8 mx-auto opacity-40 text-[#737373] dark:text-[#8E8EA0]" />
                <div>
                  <p className="font-semibold text-black dark:text-[#ECECF1]">No audits match your criteria</p>
                  <p className="text-xs text-[#737373] dark:text-[#8E8EA0] mt-1">
                    Try searching for a different repository name or session ID.
                  </p>
                </div>
                {onNewSession && (
                  <button
                    onClick={() => {
                      onNewSession();
                      onClose();
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#2525A3] text-white text-xs font-medium hover:bg-[#1E1E88] transition-colors cursor-pointer"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>Start New Codebase Audit</span>
                  </button>
                )}
              </div>
            ) : (
              filteredSessions.map((session, index) => {
                const isSelected = index === selectedIndex;
                const isActive = session.sessionId === activeSessionId;
                const displayTitle = formatChatTitle(session.userRequest, session.repoName, session.sessionId);
                const isArchive = displayTitle.startsWith("Archive:") || Boolean(session.userRequest && session.userRequest.includes(".zip"));
                const isRepo = Boolean(
                  session.repoName &&
                  session.repoName.toLowerCase() !== "general codebase audit" &&
                  !isArchive
                );
                const cleanSubtitle = session.userRequest
                  ? session.userRequest.replace(/\[System Note:[\s\S]*?\]/gi, "").trim() || displayTitle
                  : `Session ${session.sessionId.slice(0, 8)}...`;


                return (
                  <div
                    key={session.sessionId}
                    data-index={index}
                    onClick={() => {
                      onSelectSession(session.sessionId);
                      onClose();
                    }}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={`group flex items-center justify-between p-3 rounded-xl transition-all cursor-pointer select-none ${
                      isSelected
                        ? "bg-[#2525A3]/10 dark:bg-[#2525A3]/15 border border-[#2525A3]/30"
                        : "hover:bg-black/5 dark:hover:bg-white/5 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1 mr-2">
                      {/* Icon */}
                      <div className="h-9 w-9 rounded-lg flex items-center justify-center bg-black/5 dark:bg-white/10 text-[#737373] dark:text-[#8E8EA0] border border-black/10 dark:border-white/10 shrink-0">
                        {isRepo ? (
                          <GitBranch className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
                        ) : isArchive ? (
                          <FolderArchive className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
                        ) : (
                          <MessageSquare className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
                        )}
                      </div>

                      {/* Info */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-xs sm:text-sm text-black dark:text-[#ECECF1] truncate">
                            {displayTitle}
                          </span>
                          {isActive && (
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-[#2525A3]/20 text-[#2525A3] dark:text-[#A6C3EE] shrink-0">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#737373] dark:text-[#8E8EA0] truncate mt-0.5">
                          {cleanSubtitle}
                        </p>
                      </div>
                    </div>


                    {/* Right Meta (Date + Session ID) */}
                    <div className="flex items-center gap-2.5 shrink-0 text-right">
                      <div className="hidden sm:flex flex-col items-end text-[11px] text-[#737373] dark:text-[#8E8EA0]">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatTimestamp(session.lastUpdateTime || session.startedAt)}
                        </span>
                        <span className="font-mono text-[10px] opacity-70">
                          {session.sessionId.slice(0, 8)}...
                        </span>
                      </div>
                      <ArrowRight
                        className={`h-4 w-4 transition-transform ${
                          isSelected ? "text-[#2525A3] dark:text-[#A6C3EE] translate-x-1" : "text-transparent"
                        }`}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Bottom Footer Info / Keyboard Shortcuts */}
          <div className="px-4 py-2.5 border-t border-black/10 dark:border-white/10 bg-[#F9F9F9] dark:bg-[#1E1E1E] flex items-center justify-between text-[11px] text-[#737373] dark:text-[#8E8EA0]">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <kbd className="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 font-mono text-[10px]">↑</kbd>
                <kbd className="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 font-mono text-[10px]">↓</kbd>
                <span>to navigate</span>
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/10 font-mono text-[10px]">↵</kbd>
                <span>to open</span>
              </span>
            </div>
            <span>
              {filteredSessions.length} {filteredSessions.length === 1 ? "audit" : "audits"}
            </span>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
