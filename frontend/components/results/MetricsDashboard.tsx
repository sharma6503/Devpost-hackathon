"use client";

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import type { ReviewMetrics } from "@/types/adk";
import { spring } from "@/lib/motion";
import { MetricsChart } from "@/components/results/MetricsChart";
import { ShieldAlert, ShieldCheck, AlertTriangle, Info, Activity } from "lucide-react";

interface MetricsDashboardProps {
  metrics: ReviewMetrics;
  chartB64?: string;
}

function normalise(v: number | undefined): number {
  if (v == null) return 0;
  return v <= 10 ? Math.round(v * 10) : Math.round(v);
}

const EXPERT_SCORES = [
  { key: "security"     as const, label: "Security & IAM",         bar: "bg-gradient-to-r from-error/80 to-error",           glow: "glow-red",   track: "bg-error/15",         textColor: "text-error" },
  { key: "quality"      as const, label: "Code Quality & Style",    bar: "bg-gradient-to-r from-primary/80 to-primary",       glow: "glow-cyan",  track: "bg-primary/15",       textColor: "text-primary" },
  { key: "architecture" as const, label: "ADK Multi-Agent Arch",    bar: "bg-gradient-to-r from-[#2525A3] to-[#3B3BE8]",     glow: "glow-cyan",  track: "bg-[#0E1F3D]/40",     textColor: "text-[#A6C3EE]" },
  { key: "governance"   as const, label: "Standards & Governance",  bar: "bg-gradient-to-r from-secondary/80 to-secondary",   glow: "glow-amber", track: "bg-secondary/15",     textColor: "text-secondary" },
  { key: "validation"   as const, label: "Static Code Validation",  bar: "bg-gradient-to-r from-tertiary/80 to-tertiary",     glow: "glow-green", track: "bg-tertiary/15",      textColor: "text-tertiary" },
];

const SEVERITIES = [
  { key: "critical" as const, label: "Critical Threat", icon: ShieldAlert,    color: "text-error",     bg: "bg-error/10",     border: "border-error/30",     glow: "glow-red" },
  { key: "high"     as const, label: "High Risk",       icon: AlertTriangle,  color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30", glow: "glow-amber" },
  { key: "medium"   as const, label: "Medium Finding",  icon: Info,           color: "text-primary",   bg: "bg-primary/10",   border: "border-primary/30",   glow: "glow-cyan" },
  { key: "low"      as const, label: "Low / Note",      icon: ShieldCheck,    color: "text-tertiary",  bg: "bg-tertiary/10",  border: "border-tertiary/30",  glow: "glow-green" },
];

export function MetricsDashboard({ metrics }: { metrics: ReviewMetrics }) {
  const scores   = metrics?.scores   ?? {};
  const severity = metrics?.severity ?? {};

  return (
    <div className="space-y-6">
      {/* Severity Bento Badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {SEVERITIES.map((s, i) => {
          const Icon = s.icon;
          const count = severity[s.key] ?? 0;
          return (
            <motion.div
              key={s.key}
              role="img"
              aria-label={`${s.label}: ${count} finding${count !== 1 ? "s" : ""}`}
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.1 + i * 0.05, type: "spring", stiffness: 240, damping: 18 }}
              className={`flex flex-col p-4 rounded-xl border ${s.border} ${s.bg} backdrop-blur-md relative overflow-hidden group`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                  {s.label}
                </span>
                <Icon className={`w-4 h-4 ${s.color}`} />
              </div>
              <CountUp value={count} className={`font-headline text-3xl font-bold ${s.color} tracking-tight`} />
              <div className="text-[9px] font-mono text-slate-500 dark:text-slate-400 mt-1 uppercase">
                {count === 0 ? "Zero incidents" : "Requires attention"}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Domain score progress bars */}
      <div className="glass-panel p-5 rounded-2xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#1E1E1E] shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-black/10 dark:border-white/10 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#2525A3] dark:text-[#A6C3EE]" />
            <h3 className="font-headline font-bold text-sm text-black dark:text-[#ECECF1] uppercase tracking-wider">
              Domain Health Telemetry
            </h3>
          </div>
          <span className="text-[10px] font-mono text-slate-500 dark:text-slate-400 uppercase">0–100 Normalized Scale</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-1">
          {EXPERT_SCORES.map((m, i) => (
            <ScoreBar
              key={m.key}
              label={m.label}
              score={normalise(scores[m.key])}
              bar={m.bar}
              track={m.track}
              textColor={m.textColor}
              index={i}
            />
          ))}
        </div>
      </div>

      {/* Total issues summary & findings chart */}
      {Object.keys(metrics?.category ?? {}).length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
          <MetricsChart metrics={metrics} />
        </motion.div>
      )}
    </div>
  );
}

function ScoreBar({
  label, score, bar, track, textColor, index,
}: {
  label: string; score: number; bar: string; track: string; textColor: string; index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 + index * 0.05 }}
      className="p-4 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.03] shadow-xs space-y-2.5"
    >
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-700 dark:text-slate-300 font-medium font-sans">{label}</span>
        <CountUp value={score} suffix="%" className={`text-xs font-mono font-bold ${textColor}`} />
      </div>
      <div className={`h-2 rounded-full ${track} overflow-hidden`}>
        <motion.div
          className={`h-full rounded-full ${bar}`}
          initial={{ width: "0%" }}
          animate={{ width: `${score}%` }}
          transition={{ delay: 0.3 + index * 0.05, duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </motion.div>
  );
}

function CountUp({
  value, suffix = "", className = "font-headline text-3xl font-bold text-black dark:text-white",
}: {
  value: number; suffix?: string; className?: string;
}) {
  const mv = useMotionValue(0);
  const springVal = useSpring(mv, spring.counter);
  const display = useTransform(springVal, (v) => `${Math.round(v)}${suffix}`);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => { mv.set(value); }, [value, mv]);
  return <motion.span ref={ref} className={className}>{display}</motion.span>;
}

