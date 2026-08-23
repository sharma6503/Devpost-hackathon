"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import type { ReviewMetrics } from "@/types/adk";
import { BarChart3 } from "lucide-react";

const DOMAIN_META: Record<string, { label: string; color: string; gradient: string; scoreKey: string }> = {
  security:     { label: "Security",     color: "#ff5252", gradient: "from-red-500/80 to-red-400",       scoreKey: "security" },
  quality:      { label: "Quality",      color: "#00D1FF", gradient: "from-cyan-500/80 to-cyan-400",     scoreKey: "quality" },
  adk:          { label: "ADK Arch",     color: "#A6C3EE", gradient: "from-[#2525A3]/80 to-[#3B3BE8]", scoreKey: "architecture" },
  architecture: { label: "Architecture", color: "#A6C3EE", gradient: "from-[#2525A3]/80 to-[#3B3BE8]", scoreKey: "architecture" },
  governance:   { label: "Governance",   color: "#ffbf00", gradient: "from-amber-500/80 to-amber-400",   scoreKey: "governance" },
  validation:   { label: "Validation",   color: "#A6C3EE", gradient: "from-[#2525A3]/80 to-[#3B3BE8]",   scoreKey: "validation" },
};

function niceMax(max: number): number {
  if (max <= 4) return 4;
  const step = Math.ceil(max / 4);
  return step * 4;
}

interface MetricsChartProps {
  metrics: ReviewMetrics;
}

export function MetricsChart({ metrics }: MetricsChartProps) {
  const category = (metrics?.category ?? {}) as Record<string, number>;
  const scores = (metrics?.scores ?? {}) as Record<string, number>;
  const [hover, setHover] = useState<string | null>(null);

  const entries = Object.entries(category).filter(([k]) => DOMAIN_META[k]);
  if (!entries.length) return null;

  const rawMax = Math.max(0, ...entries.map(([, v]) => v ?? 0));
  const axisMax = niceMax(rawMax);
  const ticks = [0, axisMax / 4, axisMax / 2, (axisMax * 3) / 4, axisMax];
  const total = metrics.total ?? entries.reduce((a, [, v]) => a + (v ?? 0), 0);

  const summary =
    `Findings by domain: ` +
    entries.map(([key, count]) => `${DOMAIN_META[key].label} ${count ?? 0}`).join(", ") +
    `. ${total} total finding${total !== 1 ? "s" : ""}.`;

  return (
    <div
      role="img"
      aria-label={summary}
      className="glass-panel rounded-2xl border border-black/10 dark:border-white/10 p-6 shadow-xl bg-white dark:bg-[#1E1E1E]"
    >
      <div className="flex items-center justify-between mb-6 pb-3 border-b border-black/10 dark:border-white/10">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-[#2525A3] dark:text-[#A6C3EE]" />
          <h4 className="font-headline font-bold text-sm text-black dark:text-[#ECECF1] uppercase tracking-wider">
            Findings Distribution by Domain
          </h4>
        </div>
        <div className="px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 text-[10px] font-mono text-slate-700 dark:text-slate-300">
          <span className="text-[#2525A3] dark:text-[#A6C3EE] font-bold">{total}</span> total incidents
        </div>
      </div>

      {/* Plot area */}
      <div className="relative pl-8 pt-2" aria-hidden="true" style={{ height: 210 }}>
        {/* Gridlines + y-axis ticks */}
        {ticks.map((t) => (
          <div
            key={t}
            className="absolute inset-x-0 flex items-center pointer-events-none"
            style={{ bottom: `${(t / axisMax) * 100}%` }}
          >
            <span className="w-8 -translate-y-1/2 pr-2 text-right text-[10px] font-mono text-slate-500 dark:text-slate-400">
              {t}
            </span>
            <div className="flex-1 h-px bg-black/10 dark:bg-white/10" />
          </div>
        ))}

        {/* Bars */}
        <div className="absolute inset-0 left-8 flex items-end justify-around gap-4 pb-0.5">
          {entries.map(([key, count]) => {
            const meta = DOMAIN_META[key];
            const value = count ?? 0;
            const isHover = hover === key;
            const score = scores[meta.scoreKey];
            return (
              <div
                key={key}
                className="group relative flex h-full flex-1 flex-col items-center justify-end cursor-pointer"
                onMouseEnter={() => setHover(key)}
                onMouseLeave={() => setHover(null)}
              >
                {/* Floating Tactical Tooltip */}
                {isHover && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="absolute bottom-full z-20 mb-2 -translate-y-1 whitespace-nowrap rounded-xl border border-[#2525A3]/40 bg-white/95 dark:bg-[#2F2F2F]/95 backdrop-blur-md px-3 py-2 text-xs text-black dark:text-[#ECECF1] shadow-xl"
                  >
                    <div className="font-headline font-bold text-[#2525A3] dark:text-[#A6C3EE]">{meta.label}</div>
                    <div className="text-[11px] font-mono text-slate-600 dark:text-slate-300 mt-0.5">
                      {value} finding{value !== 1 ? "s" : ""}
                    </div>
                    {score != null && score > 0 && (
                      <div className="text-[10px] font-mono text-[#2525A3] dark:text-[#A6C3EE] mt-0.5">
                        Domain Health: {score}%
                      </div>
                    )}
                  </motion.div>
                )}

                {/* Value label */}
                <span
                  className={`mb-1.5 text-xs font-mono font-bold tabular-nums transition-colors ${
                    isHover ? "text-[#2525A3] dark:text-[#A6C3EE]" : "text-slate-600 dark:text-slate-400"
                  }`}
                >
                  {value}
                </span>

                {/* Bar with gradient and glow */}
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: `${Math.max(4, (value / axisMax) * 100)}%` }}
                  transition={{ duration: 0.7, ease: "easeOut" }}
                  className={`w-full max-w-[48px] rounded-t-lg bg-gradient-to-t ${meta.gradient} transition-all ${
                    isHover ? "brightness-125 shadow-lg" : "opacity-85"
                  }`}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* X-axis labels */}
      <div className="mt-3 flex justify-around gap-4 pl-8 pt-2 border-t border-black/10 dark:border-white/10">
        {entries.map(([key]) => (
          <span
            key={key}
            className={`flex-1 truncate text-center text-[10px] font-mono font-bold uppercase tracking-wider transition-colors ${
              hover === key ? "text-[#2525A3] dark:text-[#A6C3EE]" : "text-slate-600 dark:text-slate-400"
            }`}
          >
            {DOMAIN_META[key].label}
          </span>
        ))}
      </div>
    </div>
  );
}

