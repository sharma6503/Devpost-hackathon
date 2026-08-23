"use client";

import { motion } from "framer-motion";

const GRADE_STYLES: Record<string, { color: string; bg: string; border: string; glow: string; stroke: string }> = {
  A: { color: "text-tertiary", bg: "bg-tertiary/10", border: "border-tertiary/40", glow: "glow-green", stroke: "#00E639" },
  B: { color: "text-primary", bg: "bg-primary/10", border: "border-primary/40", glow: "glow-cyan", stroke: "#00D1FF" },
  C: { color: "text-secondary", bg: "bg-secondary/10", border: "border-secondary/40", glow: "glow-amber", stroke: "#ffbf00" },
  D: { color: "text-amber-500", bg: "bg-amber-500/10", border: "border-amber-500/40", glow: "glow-amber", stroke: "#f59e0b" },
  F: { color: "text-error", bg: "bg-error/10", border: "border-error/40", glow: "glow-red", stroke: "#ff5252" },
};

interface ScoreGradeProps {
  grade?: string;
  score?: number;
}

export function ScoreGrade({ grade = "?", score }: ScoreGradeProps) {
  const letter = grade?.trim().toUpperCase().charAt(0) ?? "?";
  const styles = GRADE_STYLES[letter] ?? GRADE_STYLES["C"];
  const pct = score ?? (letter === "A" ? 95 : letter === "B" ? 82 : letter === "C" ? 70 : 45);

  const label =
    letter === "?"
      ? "Audit grade not yet available"
      : `Audit grade ${letter}${score != null ? `, score ${score} of 100` : ""}`;

  return (
    <motion.div
      role="img"
      aria-label={label}
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 220, damping: 18 }}
      className="relative flex flex-col items-center justify-center p-1"
    >
      <div className={`relative w-24 h-24 rounded-full flex items-center justify-center border ${styles.border} ${styles.bg} ${styles.glow} backdrop-blur-md`}>
        {/* Glowing SVG Ring */}
        <svg className="absolute inset-0 w-full h-full -rotate-90">
          <circle
            className="text-surface-container-highest"
            cx="48"
            cy="48"
            fill="transparent"
            r="42"
            stroke="currentColor"
            strokeWidth="3"
            opacity="0.3"
          />
          <circle
            cx="48"
            cy="48"
            fill="transparent"
            r="42"
            stroke={styles.stroke}
            strokeDasharray={264}
            strokeDashoffset={264 - (264 * Math.min(100, Math.max(0, pct))) / 100}
            strokeLinecap="round"
            strokeWidth="4"
          />
        </svg>

        <div className="flex flex-col items-center z-10">
          <span className={`font-headline text-3xl font-bold tracking-tight ${styles.color}`}>{letter}</span>
          {score != null && (
            <span className="text-[10px] font-mono text-slate-400 -mt-0.5 tracking-tighter">{score}%</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

