"use client";

import { useState } from "react";
import { Trash2, Plus, Loader2, MessageSquare, Check, X, Terminal, Shield } from "lucide-react";
import { formatChatTitle } from "@/lib/session";

export interface SessionItem {
  sessionId: string;
  userRequest?: string;
  startedAt?: number;
  grade?: string;
  adkAlive?: boolean;
}

interface SessionsTabProps {
  sessions: SessionItem[];
  activeSessionId: string | null;
  userId: string;
  loading?: boolean;
  offline?: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onNew: () => void;
}

function repoLabel(req?: string, sid?: string): string {
  return formatChatTitle(req, undefined, sid);
}


function timeAgo(ts?: number): string {
  if (!ts) return "recently";
  const m = Math.floor((Date.now() - ts) / 60_000);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d > 0) return `${d}d ago`;
  if (h > 0) return `${h}h ago`;
  if (m > 0) return `${m}m ago`;
  return "just now";
}

export function SessionsTab({
  sessions,
  activeSessionId,
  userId,
  loading,
  offline,
  onSelect,
  onDelete,
  onNew,
}: SessionsTabProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  return (
    <div className="space-y-3 font-sans">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">
          ARCHIVED AUDITS ({sessions.length})
        </span>
        <button
          onClick={onNew}
          className="inline-flex items-center gap-1 rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs font-mono font-bold text-primary transition-all hover:bg-primary hover:text-black cursor-pointer"
        >
          <Plus className="h-3 w-3" /> New
        </button>
      </div>

      {offline && (
        <p className="rounded-xl border border-secondary/30 bg-secondary/10 px-3 py-2 text-xs font-mono text-secondary">
          Showing cached offline records — backend synchronization unavailable.
        </p>
      )}

      {loading && sessions.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-8 text-xs font-mono text-slate-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Loading audit history…
        </div>
      ) : sessions.length === 0 ? (
        <p className="px-2 py-8 text-center text-xs font-mono text-slate-500">
          No audit runs registered for operator &lsquo;{userId ? `${userId.slice(0, 10)}` : "anonymous"}&rsquo;.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {sessions.map((s) => {
            const current = s.sessionId === activeSessionId;
            const confirming = confirmId === s.sessionId;
            const letter = s.grade ? s.grade.trim().charAt(0).toUpperCase() : null;
            return (
              <li key={s.sessionId}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(s.sessionId)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(s.sessionId);
                    }
                  }}
                  className={`group flex cursor-pointer items-center gap-2.5 rounded-xl border p-2.5 transition-all ${
                    current
                      ? "border-[#2525A3]/50 bg-[#2525A3]/10 shadow-lg"
                      : "border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.03] hover:bg-black/5 dark:hover:bg-white/[0.06] hover:border-black/20 dark:hover:border-white/20"
                  }`}
                >
                  <Terminal
                    className={`h-4 w-4 shrink-0 ${current ? "text-[#2525A3] dark:text-[#A6C3EE]" : "text-slate-500 dark:text-slate-400"}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-black dark:text-[#ECECF1]">{repoLabel(s.userRequest, s.sessionId)}</p>
                    <p

                      className="font-mono text-[10px] text-slate-500 dark:text-slate-400 mt-0.5"
                      title={s.startedAt ? new Date(s.startedAt).toLocaleString() : undefined}
                    >
                      {s.sessionId.slice(0, 8)} · {timeAgo(s.startedAt)}
                    </p>
                  </div>

                  {letter && (
                    <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-mono font-bold border ${
                      letter === "A" ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" :
                      letter === "B" ? "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/30" :
                      "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
                    }`}>
                      {letter}
                    </span>
                  )}

                  {confirming ? (
                    <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => {
                          onDelete(s.sessionId);
                          setConfirmId(null);
                        }}
                        title="Confirm delete"
                        className="rounded-lg p-1 text-red-500 hover:bg-red-500/20 cursor-pointer"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => setConfirmId(null)}
                        title="Cancel"
                        className="rounded-lg p-1 text-slate-500 dark:text-slate-400 hover:bg-black/5 dark:hover:bg-white/10 cursor-pointer"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmId(s.sessionId);
                      }}
                      title="Delete session"
                      className="shrink-0 rounded-lg p-1 text-slate-400 hover:text-red-500 hover:bg-red-500/10 opacity-0 transition-all group-hover:opacity-100 cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

