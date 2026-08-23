"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import {
  FileCode,
  Check,
  Copy,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
  Bot,
  User,
  ShieldCheck,
  ShieldAlert,
  Code2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  Layers,
  Terminal,
  GitPullRequest,
  GitBranch,
  Cpu,
  FileCheck,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Wrench,
  ArrowRight,
  FolderArchive,
  BookOpen,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";
import type { AdkEvent, LogEntry } from "@/types/adk";

export const AGENT_LABELS_LOCAL: Record<
  string,
  { label: string; bg: string; border: string; text: string; iconBg: string }
> = {
  ingestion_agent: {
    label: "Ingestion Agent",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
    text: "text-blue-500 dark:text-blue-400",
    iconBg: "bg-blue-500",
  },
  confluence_rules_agent: {
    label: "Confluence Rules Analyst",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
    text: "text-blue-500 dark:text-blue-400",
    iconBg: "bg-blue-500",
  },
  planning_agent: {
    label: "Strategic Planning Lead",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  code_quality_expert: {
    label: "Quality Expert",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  security_expert: {
    label: "Security Architect",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    text: "text-red-500 dark:text-red-400",
    iconBg: "bg-red-500",
  },
  architecture_and_framework_expert: {
    label: "Architecture Expert",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    text: "text-amber-500 dark:text-amber-400",
    iconBg: "bg-amber-500",
  },
  governance_expert: {
    label: "Governance Specialist",
    bg: "bg-slate-500/10",
    border: "border-slate-500/30",
    text: "text-slate-600 dark:text-slate-300",
    iconBg: "bg-slate-500",
  },
  code_validator_agent: {
    label: "Validation Engine",
    bg: "bg-cyan-500/10",
    border: "border-cyan-500/30",
    text: "text-cyan-600 dark:text-cyan-400",
    iconBg: "bg-cyan-500",
  },
  evaluation_expert: {
    label: "Evaluation Expert",
    bg: "bg-neutral-500/10",
    border: "border-neutral-500/30",
    text: "text-neutral-600 dark:text-neutral-300",
    iconBg: "bg-neutral-500",
  },
  revision_agent: {
    label: "Revision Coordinator",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  synthesis_agent: {
    label: "Synthesis Specialist",
    bg: "bg-[#0E1F3D]/20",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  metrics_agent: {
    label: "Metrics Analyst",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  html_agent: {
    label: "HTML Report Generator",
    bg: "bg-indigo-500/10",
    border: "border-indigo-500/30",
    text: "text-indigo-600 dark:text-indigo-400",
    iconBg: "bg-indigo-500",
  },
  followup_agent: {
    label: "Follow-up Q&A Specialist",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  quality_expert: {
    label: "Quality Expert",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
    text: "text-blue-500 dark:text-blue-400",
    iconBg: "bg-blue-500",
  },
  adk_expert: {
    label: "Google ADK Expert",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    text: "text-amber-500 dark:text-amber-400",
    iconBg: "bg-amber-500",
  },
  remediation_agent: {
    label: "Remediation Engineer",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  learning_agent: {
    label: "Continuous Learning Agent",
    bg: "bg-rose-500/10",
    border: "border-rose-500/30",
    text: "text-rose-600 dark:text-rose-400",
    iconBg: "bg-rose-500",
  },
  remediation_planner: {
    label: "Remediation Strategist",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  remediation_executor: {
    label: "Remediation Automation Engine",
    bg: "bg-[#2525A3]/10",
    border: "border-[#2525A3]/30",
    text: "text-[#2525A3] dark:text-[#A6C3EE]",
    iconBg: "bg-[#2525A3]",
  },
  system: {
    label: "System Orchestrator",
    bg: "bg-black/5 dark:bg-white/5",
    border: "border-black/10 dark:border-white/10",
    text: "text-black dark:text-[#ECECF1]",
    iconBg: "bg-[#2525A3]",
  },
};

export function ChatCodeBlock({ children, className, filename }: { children: any; className?: string; filename?: string }) {
  const [copied, setCopied] = useState(false);
  const codeText = String(children).replace(/\n$/, "");
  const match = /language-(\w+)/.exec(className || "");
  let lang = match ? match[1] : "";

  if (!lang && filename) {
    if (filename.endsWith(".py")) lang = "python";
    else if (filename.endsWith(".ts") || filename.endsWith(".tsx")) lang = "typescript";
    else if (filename.endsWith(".js") || filename.endsWith(".jsx")) lang = "javascript";
    else if (filename.endsWith(".json")) lang = "json";
    else if (filename.endsWith(".toml")) lang = "toml";
    else if (filename.endsWith(".yaml") || filename.endsWith(".yml")) lang = "yaml";
    else if (filename.includes("Dockerfile")) lang = "dockerfile";
    else if (filename.endsWith(".sh")) lang = "bash";
  }

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(codeText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-3 select-text font-mono overflow-hidden rounded-xl border border-black/10 dark:border-white/10 bg-[#F6F8FA] dark:bg-[#171717] shadow-xs">
      <div className="flex items-center justify-between px-3.5 py-2 bg-black/[0.03] dark:bg-[#1E1E1E] border-b border-black/5 dark:border-white/5 text-[#737373] dark:text-[#8E8EA0] font-mono text-[11px] select-none">
        <div className="flex items-center gap-2">
          <FileCode className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
          <span className="font-semibold text-black dark:text-[#ECECF1] uppercase tracking-wider">{lang || filename || "CODE"}</span>
        </div>
        <button
          onClick={handleCopy}
          className="px-2.5 py-1 rounded-md bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-black dark:text-[#ECECF1] transition-all cursor-pointer flex items-center gap-1 text-xs"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-[#2525A3] dark:text-[#A6C3EE]" />
              <span className="text-[#2525A3] dark:text-[#A6C3EE] font-medium">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-xs text-black dark:text-[#ECECF1] leading-relaxed font-mono custom-scrollbar select-text bg-[#F6F8FA] dark:bg-[#171717]">
        <code>{children}</code>
      </pre>
    </div>
  );
}

export const chatMarkdownComponents = {
  h1: ({ children }: any) => (
    <h1 className="text-base font-headline font-bold text-black dark:text-white mt-4 mb-2 border-b border-black/10 dark:border-white/10 pb-1 select-text">
      {children}
    </h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="text-sm font-headline font-semibold text-[#2525A3] dark:text-[#A6C3EE] mt-3.5 mb-1.5 select-text">
      {children}
    </h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-xs font-headline font-semibold text-black dark:text-white mt-3 mb-1 select-text">
      {children}
    </h3>
  ),
  table: ({ children }: any) => (
    <div className="overflow-x-auto my-3 rounded-xl border border-black/10 dark:border-white/10 shadow-sm bg-white dark:bg-[#171717]">
      <table className="w-full text-xs border-collapse font-sans">{children}</table>
    </div>
  ),
  thead: ({ children }: any) => (
    <thead className="bg-black/[0.03] dark:bg-[#1E1E1E] border-b border-black/10 dark:border-white/10">{children}</thead>
  ),
  tbody: ({ children }: any) => <tbody className="divide-y divide-black/5 dark:divide-white/5">{children}</tbody>,
  tr: ({ children }: any) => <tr className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors">{children}</tr>,
  th: ({ children }: any) => (
    <th className="px-3.5 py-2 text-left text-[11px] font-mono font-semibold text-[#737373] dark:text-[#8E8EA0] uppercase tracking-wider whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="px-3.5 py-2 text-xs text-[#2A2A2A] dark:text-[#ECECF1] align-top leading-relaxed">{children}</td>
  ),
  code: ({ children, className }: any) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return <ChatCodeBlock className={className}>{children}</ChatCodeBlock>;
    }
    return (
      <code className="px-1.5 py-0.5 rounded-md bg-black/5 dark:bg-[#171717] border border-black/10 dark:border-white/10 text-[#2525A3] dark:text-[#A6C3EE] text-xs font-mono select-text">
        {children}
      </code>
    );
  },
  p: ({ children }: any) => (
    <p className="text-xs sm:text-[13.5px] text-[#2A2A2A] dark:text-[#ECECF1] font-sans font-normal leading-relaxed mb-2.5 last:mb-0 select-text">{children}</p>
  ),
  ul: ({ children }: any) => (
    <ul className="list-disc pl-5 my-2 space-y-1 text-xs sm:text-[13px] text-[#2A2A2A] dark:text-[#ECECF1] select-text">{children}</ul>
  ),
  ol: ({ children }: any) => (
    <ol className="list-decimal pl-5 my-2 space-y-1 text-xs sm:text-[13px] text-[#2A2A2A] dark:text-[#ECECF1] select-text">{children}</ol>
  ),
  li: ({ children }: any) => <li className="leading-relaxed select-text">{children}</li>,
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-2 border-[#2525A3] pl-3 my-2 text-xs text-[#737373] dark:text-[#8E8EA0] italic select-text">
      {children}
    </blockquote>
  ),
};

/* ─── Structured Response Type Parsers ─────────────────────────────────────────── */

function tryParseStructuredJson(raw: string): { type: "planning" | "remediation" | "evaluation" | "json"; data: any } | null {
  if (!raw || typeof raw !== "string") return null;

  let trimmed = raw.trim();

  // Strip markdown code fences if wrapped in ```json ... ```
  if (trimmed.startsWith("```")) {
    trimmed = trimmed.replace(/^```(?:json)?\s*\n?/, "").replace(/\n?```\s*$/, "").trim();
  }

  // Attempt direct JSON parse
  let parsed: any = null;
  try {
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      parsed = JSON.parse(trimmed);
    } else {
      // Look for embedded JSON object in text
      const jsonMatch = trimmed.match(/(\{[\s\S]*\})/);
      if (jsonMatch) {
        parsed = JSON.parse(jsonMatch[1]);
      }
    }
  } catch {
    return null;
  }

  if (!parsed || typeof parsed !== "object") return null;

  // 1. Planning Strategy Output
  if (
    parsed.assignments !== undefined ||
    (parsed.strategy !== undefined && parsed.is_large_codebase !== undefined)
  ) {
    return { type: "planning", data: parsed };
  }

  // 2. Remediation Output
  if (
    parsed.pr_title !== undefined ||
    (Array.isArray(parsed.changes) && parsed.changes.length > 0) ||
    (parsed.target_repo !== undefined && parsed.pr_branch !== undefined)
  ) {
    return { type: "remediation", data: parsed };
  }

  // 3. Evaluation Quality Gate Output (evaluation_expert)
  if (
    Array.isArray(parsed.scores) ||
    parsed.overall_grade !== undefined ||
    parsed.weakest_agent !== undefined ||
    (parsed.passed !== undefined && (parsed.grade !== undefined || parsed.summary !== undefined))
  ) {
    return { type: "evaluation", data: parsed };
  }

  return { type: "json", data: parsed };
}

function cleanUserPrompt(raw: string): string {
  if (!raw) return "";
  // Strip system prompt note injected on zip uploads
  let cleaned = raw.replace(/\[System Note:[\s\S]*?\]/gi, "").trim();
  return cleaned || raw;
}

/* ─── Expert Icon and Color Resolver for Planning Card ────────────────────────── */

function getExpertBadge(expertName: string) {
  const norm = (expertName || "").toLowerCase();
  if (norm.includes("security")) {
    return {
      label: "Security Architect",
      icon: <ShieldAlert className="h-3.5 w-3.5 text-red-500 shrink-0" />,
      color: "border-red-500/20 bg-red-500/5 text-red-600 dark:text-red-400",
    };
  }
  if (norm.includes("quality")) {
    return {
      label: "Quality Expert",
      icon: <Code2 className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />,
      color: "border-[#2525A3]/20 bg-[#2525A3]/5 text-[#2525A3] dark:text-[#A6C3EE]",
    };
  }
  if (norm.includes("adk") || norm.includes("arch")) {
    return {
      label: "Google ADK Expert",
      icon: <Cpu className="h-3.5 w-3.5 text-amber-500 shrink-0" />,
      color: "border-amber-500/20 bg-amber-500/5 text-amber-600 dark:text-amber-400",
    };
  }
  if (norm.includes("gov") || norm.includes("rule")) {
    return {
      label: "Governance Specialist",
      icon: <FileCheck className="h-3.5 w-3.5 text-slate-500 shrink-0" />,
      color: "border-slate-500/20 bg-slate-500/5 text-slate-600 dark:text-slate-300",
    };
  }
  return {
    label: expertName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    icon: <Bot className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />,
    color: "border-[#2525A3]/20 bg-[#2525A3]/5 text-[#2525A3] dark:text-[#A6C3EE]",
  };
}

/* ─── 1. Structured Planning Strategy Card Component ───────────────────────────── */

function StrategicPlanningCard({ data }: { data: any }) {
  const assignments: any[] = Array.isArray(data.assignments) ? data.assignments : [];
  const isLarge = Boolean(data.is_large_codebase);

  return (
    <div className="my-3 rounded-2xl border border-[#2525A3]/25 bg-[#2525A3]/[0.03] dark:bg-[#0E1F3D]/20 p-4 sm:p-5 shadow-xs space-y-4 select-text">
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#2525A3]/15 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#2525A3] text-white shadow-xs">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs sm:text-sm font-semibold text-black dark:text-[#ECECF1]">
              Review Strategy & Multi-Agent Distribution
            </h3>
            <p className="text-[11px] text-[#737373] dark:text-[#8E8EA0]">
              Strategic task decomposition across autonomous domain experts
            </p>
          </div>
        </div>

        <span
          className={`px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium border ${
            isLarge
              ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
              : "bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border-[#2525A3]/20"
          }`}
        >
          {isLarge ? "Partitioned Swarm (Large Codebase)" : "Comprehensive Audit (Standard)"}
        </span>
      </div>

      {/* Strategy Description */}
      {data.strategy && (
        <div className="rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5 p-3 text-xs sm:text-[13px] text-[#2A2A2A] dark:text-[#ECECF1] leading-relaxed">
          <span className="font-semibold text-[#2525A3] dark:text-[#A6C3EE] mr-1.5">Strategy:</span>
          {data.strategy}
        </div>
      )}

      {/* Assignments Fleet Grid */}
      {assignments.length > 0 && (
        <div className="space-y-2">
          <div className="text-[11px] font-mono font-medium uppercase tracking-wider text-[#737373] dark:text-[#8E8EA0]">
            Assigned Fleet Specialists ({assignments.length})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {assignments.map((item, idx) => {
              const badge = getExpertBadge(item.expert_name);
              const modules = Array.isArray(item.assigned_modules)
                ? item.assigned_modules.join(", ")
                : String(item.assigned_modules || "all");

              return (
                <div
                  key={idx}
                  className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#1A1A1A] p-3 shadow-2xs space-y-2"
                >
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5">
                      {badge.icon}
                      <span className="text-xs font-semibold text-black dark:text-[#ECECF1]">
                        {badge.label}
                      </span>
                    </div>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-mono bg-black/5 dark:bg-white/5 text-[#737373] dark:text-[#8E8EA0]">
                      Scope: {modules}
                    </span>
                  </div>

                  {item.focus_areas && (
                    <p className="text-[11.5px] text-[#555] dark:text-[#A0A0B0] leading-relaxed">
                      {item.focus_areas}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── 2. Structured Remediation Pull Request Card Component ─────────────────────── */

function RemediationPlanCard({ data }: { data: any }) {
  const [expandedFiles, setExpandedFiles] = useState<Record<number, boolean>>({ 0: true });
  const changes: any[] = Array.isArray(data.changes) ? data.changes : [];

  const toggleFile = (idx: number) => {
    setExpandedFiles((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const getFindingColor = (findingId?: string) => {
    const fid = (findingId || "").toUpperCase();
    if (fid.startsWith("SEC")) return "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20";
    if (fid.startsWith("BUG")) return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20";
    if (fid.startsWith("GOV")) return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20";
    if (fid.startsWith("MODEL")) return "bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border-[#2525A3]/20";
    return "bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border-[#2525A3]/20";
  };

  return (
    <div className="my-4 rounded-2xl border border-[#2525A3]/30 bg-[#2525A3]/[0.03] dark:bg-[#0E1F3D]/20 p-4 sm:p-5 shadow-xs space-y-4 select-text">
      {/* PR Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#2525A3]/15 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#2525A3] text-white shadow-xs">
            <GitPullRequest className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs sm:text-sm font-semibold text-black dark:text-[#ECECF1]">
              {data.pr_title || "Automated Remediation Pull Request"}
            </h3>
            <div className="flex items-center gap-2 mt-0.5 text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0]">
              <span className="flex items-center gap-1">
                <GitBranch className="h-3 w-3 text-[#2525A3] dark:text-[#A6C3EE]" />
                {data.base_branch || "main"} ← {data.pr_branch || "agent_guardian/review"}
              </span>
              {data.target_repo && (
                <>
                  <span>•</span>
                  <span>{data.target_repo}</span>
                </>
              )}
            </div>
          </div>
        </div>

        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/20">
          {changes.length} {changes.length === 1 ? "Fix Ready" : "Fixes Ready"}
        </span>
      </div>

      {/* PR Markdown Body Summary */}
      {data.pr_body && (
        <div className="text-xs sm:text-[13px] text-black dark:text-[#ECECF1] leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={chatMarkdownComponents}>
            {data.pr_body}
          </ReactMarkdown>
        </div>
      )}

      {/* Changes / Files Accordion */}
      {changes.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between text-[11px] font-mono font-medium uppercase tracking-wider text-[#737373] dark:text-[#8E8EA0]">
            <span>Automated File Patches ({changes.length})</span>
            <button
              onClick={() => {
                const allOpen = changes.reduce((acc, _, i) => ({ ...acc, [i]: true }), {});
                setExpandedFiles(allOpen);
              }}
              className="hover:text-[#2525A3] dark:hover:text-[#A6C3EE] transition-colors cursor-pointer text-[10px] lowercase"
            >
              expand all
            </button>
          </div>

          <div className="space-y-2.5">
            {changes.map((ch, idx) => {
              const isOpen = Boolean(expandedFiles[idx]);
              return (
                <div
                  key={idx}
                  className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#1A1A1A] overflow-hidden shadow-2xs"
                >
                  {/* File Header Accordion Trigger */}
                  <div
                    onClick={() => toggleFile(idx)}
                    className="flex items-center justify-between p-3 bg-black/[0.02] dark:bg-white/[0.02] hover:bg-black/[0.04] dark:hover:bg-white/[0.04] transition-colors cursor-pointer select-none"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {isOpen ? (
                        <ChevronDown className="h-4 w-4 text-[#737373] dark:text-[#8E8EA0] shrink-0" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-[#737373] dark:text-[#8E8EA0] shrink-0" />
                      )}
                      <FileCode className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />
                      <span className="font-mono text-xs font-semibold text-black dark:text-[#ECECF1] truncate">
                        {ch.file_path}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {ch.finding_id && (
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-mono font-medium border ${getFindingColor(ch.finding_id)}`}>
                          {ch.finding_id}
                        </span>
                      )}
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-black/5 dark:bg-white/5 text-[#737373] dark:text-[#8E8EA0] uppercase">
                        {ch.change_type || "modify"}
                      </span>
                    </div>
                  </div>

                  {/* Expanded Content */}
                  {isOpen && (
                    <div className="p-3.5 border-t border-black/5 dark:border-white/5 space-y-2.5">
                      {ch.rationale && (
                        <p className="text-xs text-[#555] dark:text-[#A0A0B0] italic">
                          <span className="font-semibold text-black dark:text-[#ECECF1] not-italic">Rationale: </span>
                          {ch.rationale}
                        </p>
                      )}

                      {ch.replacement_snippet && (
                        <ChatCodeBlock filename={ch.file_path}>
                          {ch.replacement_snippet}
                        </ChatCodeBlock>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── 3. Structured Quality Gate Evaluation Card Component ────────────────────────── */

interface EvaluationScoreItem {
  agent: string;
  specificity?: number;
  evidence?: number;
  actionability?: number;
  avg?: number;
}

function EvaluationReportCard({ data }: { data: any }) {
  const scores: EvaluationScoreItem[] = Array.isArray(data.scores)
    ? data.scores
    : Array.isArray(data.evaluations)
    ? data.evaluations
    : [];

  const rawGrade = String(data.overall_grade || data.grade || "").toUpperCase().trim();
  const isPass =
    rawGrade === "PASS" ||
    rawGrade === "A" ||
    rawGrade === "B" ||
    data.passed === true;

  const displayGrade = rawGrade || (isPass ? "PASS" : "FAIL");
  const weakestAgent = data.weakest_agent;
  const weakestDimension = data.weakest_dimension;
  const feedback = data.feedback || data.summary || data.critique || "";

  const getScoreColor = (score?: number) => {
    if (score === undefined || score === null) return "text-[#737373] dark:text-[#8E8EA0]";
    if (score >= 8) return "text-emerald-600 dark:text-emerald-400 font-semibold";
    if (score >= 6) return "text-amber-600 dark:text-amber-400 font-medium";
    return "text-red-500 dark:text-red-400 font-bold";
  };

  const getBarColor = (score?: number) => {
    if (score === undefined || score === null) return "bg-black/10 dark:bg-white/10";
    if (score >= 8) return "bg-emerald-500";
    if (score >= 6) return "bg-amber-500";
    return "bg-red-500";
  };

  return (
    <div className="my-3 rounded-2xl border border-black/10 dark:border-white/10 bg-[#FAFAFA] dark:bg-[#1A1A1A] p-4 sm:p-5 shadow-xs space-y-4 select-text">
      {/* Quality Gate Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/5 dark:border-white/5 pb-3">
        <div className="flex items-center gap-2.5">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-xl text-white shadow-xs ${
              isPass ? "bg-emerald-600" : "bg-amber-600 dark:bg-amber-500"
            }`}
          >
            {isPass ? <ShieldCheck className="h-4.5 w-4.5" /> : <ShieldAlert className="h-4.5 w-4.5" />}
          </div>
          <div>
            <h3 className="text-xs sm:text-sm font-semibold text-black dark:text-[#ECECF1] flex items-center gap-2">
              Quality Gate Evaluation
              <span className="text-[11px] font-normal text-[#737373] dark:text-[#8E8EA0]">
                (Multi-Agent Scoring)
              </span>
            </h3>
            <p className="text-[11px] text-[#737373] dark:text-[#8E8EA0]">
              Auditing citation specificity, code evidence, and remediation actionability
            </p>
          </div>
        </div>

        {/* Status Badge */}
        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 rounded-full text-xs font-mono font-bold uppercase tracking-wider border flex items-center gap-1.5 ${
              isPass
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                : "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30"
            }`}
          >
            {isPass ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
            {displayGrade === "PASS"
              ? "PASS • Threshold Met"
              : displayGrade === "FAIL"
              ? "FAIL • Revision Triggered"
              : `Grade: ${displayGrade}`}
          </span>
        </div>
      </div>

      {/* Per-Agent Score Matrix */}
      {scores.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[11px] font-mono font-medium uppercase tracking-wider text-[#737373] dark:text-[#8E8EA0]">
            <span>Domain Expert Quality Matrix</span>
            <span>Threshold: ≥ 7.0 / 10</span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#141414] shadow-2xs">
            <table className="w-full text-left text-xs border-collapse font-sans">
              <thead>
                <tr className="border-b border-black/5 dark:border-white/5 bg-black/[0.02] dark:bg-white/[0.02] text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0] uppercase">
                  <th className="py-2.5 px-3.5 font-semibold">Specialist Agent</th>
                  <th className="py-2.5 px-3 font-semibold text-center">Specificity</th>
                  <th className="py-2.5 px-3 font-semibold text-center">Evidence</th>
                  <th className="py-2.5 px-3 font-semibold text-center">Actionability</th>
                  <th className="py-2.5 px-3.5 font-semibold text-right">Avg Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5 dark:divide-white/5">
                {scores.map((sc, idx) => {
                  const badge = getExpertBadge(sc.agent);
                  const isWeakest = Boolean(
                    weakestAgent && sc.agent && sc.agent.toLowerCase().includes(String(weakestAgent).toLowerCase())
                  );
                  const avgVal = typeof sc.avg === "number" ? sc.avg : Number(sc.avg) || 0;
                  const passedThreshold = avgVal >= 7.0;

                  return (
                    <tr
                      key={idx}
                      className={`hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors ${
                        isWeakest ? "bg-red-500/[0.03] dark:bg-red-500/[0.06]" : ""
                      }`}
                    >
                      {/* Agent Name */}
                      <td className="py-2.5 px-3.5">
                        <div className="flex items-center gap-2">
                          {badge.icon}
                          <span className="font-medium text-black dark:text-[#ECECF1] text-xs">
                            {badge.label}
                          </span>
                          {isWeakest && (
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-red-500/10 text-red-500 border border-red-500/20">
                              Weakest
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Specificity */}
                      <td className="py-2.5 px-3 text-center">
                        <div className="inline-flex flex-col items-center gap-1">
                          <span className={`font-mono text-xs ${getScoreColor(sc.specificity)}`}>
                            {sc.specificity ?? "—"}/10
                          </span>
                          {sc.specificity !== undefined && (
                            <div className="w-12 h-1 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${getBarColor(sc.specificity)}`}
                                style={{ width: `${Math.min(100, ((sc.specificity ?? 0) / 10) * 100)}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Evidence */}
                      <td className="py-2.5 px-3 text-center">
                        <div className="inline-flex flex-col items-center gap-1">
                          <span className={`font-mono text-xs ${getScoreColor(sc.evidence)}`}>
                            {sc.evidence ?? "—"}/10
                          </span>
                          {sc.evidence !== undefined && (
                            <div className="w-12 h-1 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${getBarColor(sc.evidence)}`}
                                style={{ width: `${Math.min(100, ((sc.evidence ?? 0) / 10) * 100)}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Actionability */}
                      <td className="py-2.5 px-3 text-center">
                        <div className="inline-flex flex-col items-center gap-1">
                          <span className={`font-mono text-xs ${getScoreColor(sc.actionability)}`}>
                            {sc.actionability ?? "—"}/10
                          </span>
                          {sc.actionability !== undefined && (
                            <div className="w-12 h-1 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${getBarColor(sc.actionability)}`}
                                style={{ width: `${Math.min(100, ((sc.actionability ?? 0) / 10) * 100)}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Average */}
                      <td className="py-2.5 px-3.5 text-right">
                        <span
                          className={`px-2 py-0.5 rounded-md font-mono text-xs font-semibold ${
                            passedThreshold
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                              : "bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20"
                          }`}
                        >
                          {avgVal.toFixed(1)} / 10
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Weakest Specialist Callout Banner (if present and failed) */}
      {weakestAgent && !isPass && (
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-700 dark:text-amber-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="flex-1">
            <span className="font-semibold">Targeted for Refinement: </span>
            <span className="font-mono">{getExpertBadge(weakestAgent).label}</span>
            {weakestDimension && (
              <span> (Lowest Dimension: <strong className="font-mono uppercase">{weakestDimension}</strong>)</span>
            )}
          </div>
        </div>
      )}

      {/* Actionable Feedback Guidance */}
      {feedback && (
        <div className="rounded-xl border border-black/5 dark:border-white/5 bg-white dark:bg-[#141414] p-3.5 space-y-1.5 shadow-2xs">
          <div className="text-[11px] font-mono font-medium uppercase tracking-wider text-[#737373] dark:text-[#8E8EA0] flex items-center gap-1.5">
            <BookOpen className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
            <span>Auditor Feedback & Refinement Instructions</span>
          </div>
          <p className="text-xs sm:text-[13px] text-[#2A2A2A] dark:text-[#ECECF1] leading-relaxed">
            {feedback}
          </p>
        </div>
      )}
    </div>
  );
}

/* ─── Main ChatLogRow Subcomponents ─────────────────────────────────────────────────── */

export function ToolCallView({ toolData }: { toolData?: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const name = (toolData?.name as string) || "function_call";
  const args = toolData?.args ? JSON.stringify(toolData.args, null, 2) : "{}";

  return (
    <div className="my-2 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.02] overflow-hidden text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-black/[0.03] dark:bg-white/[0.04] hover:bg-black/[0.06] dark:hover:bg-white/[0.08] transition-colors cursor-pointer text-left"
      >
        <div className="flex items-center gap-2">
          <Wrench className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
          <span className="font-mono font-medium text-black dark:text-[#ECECF1]">
            Tool Call: <span className="text-[#2525A3] dark:text-[#A6C3EE]">{name}</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[#737373] dark:text-[#8E8EA0] text-[11px] font-mono">
          <span>{open ? "Hide args" : "View args"}</span>
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </div>
      </button>
      {open && (
        <pre className="p-3 text-[11px] font-mono bg-[#F6F8FA] dark:bg-[#171717] text-black dark:text-[#ECECF1] overflow-x-auto custom-scrollbar border-t border-black/5 dark:border-white/5">
          <code>{args}</code>
        </pre>
      )}
    </div>
  );
}

export function ToolResultView({ toolData }: { toolData?: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const name = (toolData?.name as string) || "tool_result";
  const resp = toolData?.response
    ? typeof toolData.response === "string"
      ? toolData.response
      : JSON.stringify(toolData.response, null, 2)
    : "{}";

  return (
    <div className="my-2 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.02] dark:bg-emerald-500/[0.03] overflow-hidden text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-emerald-500/[0.05] dark:bg-emerald-500/[0.08] hover:bg-emerald-500/[0.1] transition-colors cursor-pointer text-left"
      >
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
          <span className="font-mono font-medium text-black dark:text-[#ECECF1]">
            Tool Output: <span className="text-emerald-600 dark:text-emerald-400">{name}</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[#737373] dark:text-[#8E8EA0] text-[11px] font-mono">
          <span>{open ? "Hide result" : "View result"}</span>
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </div>
      </button>
      {open && (
        <pre className="p-3 text-[11px] font-mono bg-[#F6F8FA] dark:bg-[#171717] text-black dark:text-[#ECECF1] overflow-x-auto max-h-64 custom-scrollbar border-t border-emerald-500/10">
          <code>{resp}</code>
        </pre>
      )}
    </div>
  );
}

export function ThoughtView({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="my-2 rounded-xl border border-purple-500/20 bg-purple-500/[0.03] overflow-hidden text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-purple-600 dark:text-purple-400 hover:bg-purple-500/[0.08] transition-colors cursor-pointer text-left font-mono text-[11px]"
      >
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-purple-500" />
          <span>Chain of Thought</span>
        </div>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="p-3 text-xs text-black/80 dark:text-[#ECECF1]/80 italic border-t border-purple-500/10 leading-relaxed font-sans">
          {text}
        </div>
      )}
    </div>
  );
}

export interface ChatLogRowProps {
  entry?: LogEntry;
  turn?: number;
  author?: string;
  body?: string;
  event?: AdkEvent;
  isStreaming?: boolean;
  onInspectDelta?: (event: AdkEvent) => void;
  onInspectEvent?: (event: AdkEvent) => void;
}

export function ChatLogRow({
  entry,
  turn,
  author,
  body,
  event,
  isStreaming = false,
  onInspectDelta,
  onInspectEvent,
}: ChatLogRowProps) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  const rawAuthor = entry?.author || author || "system";
  const rawContent = entry?.text || body || "";
  const currentTurn = turn ?? 1;
  const isUser = rawAuthor === "user" || rawAuthor === "Operator" || rawAuthor === "USER";

  const currentEvent =
    entry?.rawEvent ||
    event ||
    (entry
      ? ({
          id: entry.id,
          invocationId: "active",
          author: entry.author || rawAuthor,
          content: {
            role: isUser ? "user" : "model",
            parts: rawContent ? [{ text: rawContent }] : [],
          },
          actions: entry.stateDelta ? { stateDelta: entry.stateDelta } : undefined,
          timestamp: typeof entry.timestamp === "number" ? entry.timestamp : Date.now(),
        } as AdkEvent)
      : null);

  const agentMeta = AGENT_LABELS_LOCAL[rawAuthor] || {
    label: rawAuthor.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    bg: "bg-black/5 dark:bg-white/5",
    border: "border-black/10 dark:border-white/10",
    text: "text-black dark:text-[#ECECF1]",
    iconBg: "bg-[#2525A3]",
  };

  const handleCopyText = () => {
    navigator.clipboard.writeText(rawContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Render User Message Pill (Agent Guardian Workspace Style)
  if (isUser) {
    const userPrompt = cleanUserPrompt(rawContent);

    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex justify-end my-4 px-2 select-text"
      >
        <div className="max-w-2xl px-4 py-3 rounded-3xl bg-[#F4F4F4] dark:bg-[#2F2F2F] border border-black/5 dark:border-white/10 text-black dark:text-[#ECECF1] text-xs sm:text-sm font-sans leading-relaxed shadow-xs">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={chatMarkdownComponents}>
            {userPrompt}
          </ReactMarkdown>
        </div>
      </motion.div>
    );
  }

  // Check for structured JSON outputs from agents (Planning, Remediation, etc.)
  const structured = tryParseStructuredJson(rawContent);

  // Render Assistant / Swarm Message (Agent Guardian Workspace Style)
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="group flex gap-3.5 my-5 px-2 select-text"
    >
      {/* Agent Avatar */}
      <div className="flex flex-col items-center shrink-0">
        <AgentGuardianLogo size={32} />
      </div>

      {/* Message Body Content */}
      <div className="flex-1 min-w-0 space-y-2">
        {/* Header with Agent Label */}
        <div className="flex items-center gap-2 select-none">
          <span className="text-xs font-semibold text-black dark:text-[#ECECF1]">
            {rawAuthor === "system" || rawAuthor === "root_agent" || rawAuthor === "agent_guardian" || rawAuthor === "agent"
              ? "Agent Guardian"
              : (agentMeta?.label || rawAuthor.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()))}
          </span>
          {entry?.type === "transfer" && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
              Delegation
            </span>
          )}
          {isStreaming && (
            <span className="flex items-center gap-1 text-[10px] font-mono text-[#2525A3] dark:text-[#A6C3EE] animate-pulse">
              <span className="h-1.5 w-1.5 rounded-full bg-[#2525A3]" />
              Thinking...
            </span>
          )}
        </div>

        {/* Content Render: Tool Calls, Tool Results, Thoughts, Structured Cards, or Markdown */}
        {entry?.type === "tool_call" ? (
          <ToolCallView toolData={entry.toolData} />
        ) : entry?.type === "tool_result" ? (
          <ToolResultView toolData={entry.toolData} />
        ) : entry?.type === "thought" ? (
          <ThoughtView text={entry.text} />
        ) : structured?.type === "planning" ? (
          <StrategicPlanningCard data={structured.data} />
        ) : structured?.type === "remediation" ? (
          <RemediationPlanCard data={structured.data} />
        ) : structured?.type === "evaluation" ? (
          <EvaluationReportCard data={structured.data} />
        ) : (
          <div className="text-xs sm:text-sm text-black dark:text-[#ECECF1] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={chatMarkdownComponents}>
              {rawContent}
            </ReactMarkdown>
          </div>
        )}

        {/* Agent Guardian Message Action Toolbar */}
        <div className="flex items-center gap-2 pt-1 select-none text-[#737373] dark:text-[#8E8EA0]">
          <button
            onClick={handleCopyText}
            className="p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 hover:text-black dark:hover:text-[#ECECF1] transition-colors cursor-pointer"
            title="Copy response"
            aria-label="Copy response"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" /> : <Copy className="h-3.5 w-3.5" />}
          </button>

          <button
            onClick={() => setFeedback(feedback === "up" ? null : "up")}
            className={`p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer ${
              feedback === "up" ? "text-[#2525A3] dark:text-[#A6C3EE]" : "hover:text-black dark:hover:text-[#ECECF1]"
            }`}
            title="Good response"
            aria-label="Good response"
          >
            <ThumbsUp className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => setFeedback(feedback === "down" ? null : "down")}
            className={`p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer ${
              feedback === "down" ? "text-red-400" : "hover:text-black dark:hover:text-[#ECECF1]"
            }`}
            title="Bad response"
            aria-label="Bad response"
          >
            <ThumbsDown className="h-3.5 w-3.5" />
          </button>

          {currentEvent && onInspectEvent && (
            <button
              onClick={() => onInspectEvent(currentEvent)}
              className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-[#2525A3] dark:text-[#A6C3EE] hover:text-[#1E1E88] transition-colors ml-auto cursor-pointer"
              title="Inspect raw ADK Event"
            >
              <Code2 className="h-3 w-3" />
              <span>Event</span>
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

