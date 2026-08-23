"use client";

import { motion } from "framer-motion";
import { GitPullRequest, ExternalLink, SkipForward, Clock, AlertTriangle, Check, ShieldCheck, Wrench } from "lucide-react";

type RemediationStatus =
  | ""
  | "pending_approval"
  | "created"
  | "skipped"
  | "dry_run"
  | "no_target"
  | "failed";

interface RemediationBannerProps {
  prUrl?: string;
  skipped?: boolean;
  status?: RemediationStatus;
  planSummary?: string;
  onApprove?: () => void;
  onSkip?: () => void;
  busy?: boolean;
}

function isRealPrUrl(value?: string): value is string {
  return !!value && /^https?:\/\//i.test(value.trim());
}

const SHELL =
  "flex items-center gap-3 p-4 rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#1E1E1E] backdrop-blur-md shadow-md";

export function RemediationBanner({
  prUrl,
  skipped,
  status,
  planSummary,
  onApprove,
  onSkip,
  busy,
}: RemediationBannerProps) {
  const effective: RemediationStatus =
    status ||
    (isRealPrUrl(prUrl) ? "created" : skipped ? "skipped" : "");

  // --- Created: the only state with a navigable PR link ---
  if (effective === "created" && isRealPrUrl(prUrl)) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="flex items-center justify-between gap-4 p-5 rounded-2xl border border-[#2525A3]/40 bg-gradient-to-r from-[#2525A3]/10 via-white dark:via-[#1E1E1E] to-[#2525A3]/5 shadow-xl backdrop-blur-md"
      >
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-11 h-11 rounded-xl bg-[#2525A3]/20 flex items-center justify-center text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/40 shrink-0">
            <GitPullRequest className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-[#2525A3] dark:text-[#A6C3EE]">
                Remediation Branch Merged &amp; PR Live
              </span>
              <span className="px-2 py-0.5 rounded-full bg-[#2525A3]/20 text-[#2525A3] dark:text-[#A6C3EE] text-[10px] font-mono font-bold">
                VERIFIED
              </span>
            </div>
            <p className="text-xs font-mono text-slate-700 dark:text-slate-300 truncate mt-0.5 max-w-lg">{prUrl}</p>
          </div>
        </div>
        <a
          href={prUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#2525A3] hover:bg-[#1E1E88] text-white text-xs font-headline font-bold uppercase tracking-wider transition-all shrink-0 cursor-pointer shadow-md"
        >
          <span>Inspect PR</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </motion.div>
    );
  }

  // --- Pending approval: show proposed plan and tactical Approve/Skip ---
  if (effective === "pending_approval") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-3.5 p-5 rounded-2xl border border-amber-500/40 bg-white dark:bg-[#1E1E1E] shadow-xl backdrop-blur-md"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/20 flex items-center justify-center text-amber-600 dark:text-amber-400 border border-amber-500/30">
              <Wrench className="w-4 h-4" />
            </div>
            <div>
              <p className="text-sm font-headline font-bold text-black dark:text-[#ECECF1] uppercase tracking-wide">
                Remediation Plan Ready for Deployment
              </p>
              <p className="text-xs text-slate-600 dark:text-slate-400 font-sans">
                Review AST-verified patches before initiating the remote branch commit.
              </p>
            </div>
          </div>
          <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-600 dark:text-amber-400 text-[10px] font-mono uppercase font-bold animate-pulse">
            Awaiting Approval
          </span>
        </div>

        {planSummary ? (
          <pre className="text-xs text-slate-800 dark:text-slate-200 font-mono whitespace-pre-wrap break-words max-h-48 overflow-auto rounded-xl bg-black/[0.03] dark:bg-black/40 p-3.5 border border-black/10 dark:border-white/10 custom-scrollbar">
            {planSummary}
          </pre>
        ) : null}

        {(onApprove || onSkip) && (
          <div className="flex items-center gap-3 pt-1">
            {onApprove && (
              <button
                type="button"
                onClick={onApprove}
                disabled={busy}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#2525A3] hover:bg-[#1E1E88] disabled:opacity-50 text-white font-headline text-xs font-bold uppercase tracking-wider transition-all shadow-md cursor-pointer"
              >
                <Check className="w-4 h-4" />
                <span>Approve &amp; Generate PR</span>
              </button>
            )}
            {onSkip && (
              <button
                type="button"
                onClick={onSkip}
                disabled={busy}
                className="flex items-center gap-2 px-4 py-2 rounded-xl border border-black/15 dark:border-white/15 hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50 text-slate-700 dark:text-slate-300 font-headline text-xs font-bold uppercase tracking-wider transition-all cursor-pointer"
              >
                <SkipForward className="w-4 h-4" />
                <span>Skip Remediation</span>
              </button>
            )}
          </div>
        )}
      </motion.div>
    );
  }

  // --- Failed ---
  if (effective === "failed") {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={SHELL}>
        <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
        <span className="text-xs font-mono text-slate-700 dark:text-slate-300">
          Remediation execution encountered non-recoverable AST checks — no branch was pushed.
        </span>
      </motion.div>
    );
  }

  // --- Skipped / dry-run / no-target ---
  if (effective === "skipped" || effective === "dry_run" || effective === "no_target") {
    const msg =
      effective === "dry_run"
        ? "Remediation executed in dry-run mode — AST verified without remote push."
        : effective === "no_target"
        ? "Remediation skipped — no remote GitHub/Bitbucket repository credentials provided."
        : "Automated remediation was bypassed for this review turn.";
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={SHELL}>
        <SkipForward className="w-4 h-4 text-slate-500 dark:text-slate-400 shrink-0" />
        <span className="text-xs font-mono text-slate-600 dark:text-slate-400">{msg}</span>
      </motion.div>
    );
  }

  return null;
}

