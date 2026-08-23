"use client";
import { useEffect } from "react";
import type { PipelinePhase } from "@/types/adk";

const PHASE_EMOJI: Record<string, string> = {
  ingestion:   "📥",
  planning:    "🗺️",
  analysis:    "🔍",
  reporting:   "📄",
  remediation: "🔧",
};

export function useTabTitle({
  phases,
  isComplete,
  isRunning,
}: {
  phases: PipelinePhase[];
  isComplete: boolean;
  isRunning: boolean;
}) {
  useEffect(() => {
    if (isComplete) {
      document.title = "✅ Complete — Agent Guardian";
      return;
    }
    if (!isRunning) {
      document.title = "Agent Guardian";
      return;
    }
    const active = phases.find((p) => p.status === "active");
    if (active) {
      const emoji = PHASE_EMOJI[active.id] ?? "⏳";
      document.title = `${emoji} ${active.label} — Agent Guardian`;
    } else {
      document.title = "⏳ Starting — Agent Guardian";
    }
  }, [phases, isComplete, isRunning]);

  // Reset on unmount
  useEffect(() => () => { document.title = "Agent Guardian"; }, []);
}
