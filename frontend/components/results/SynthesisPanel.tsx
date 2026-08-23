"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, FileText, Sparkles, ShieldCheck } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface SynthesisPanelProps {
  content?: string;
}

export function SynthesisPanel({ content }: SynthesisPanelProps) {
  const [open, setOpen] = useState(true);

  if (!content) return null;

  return (
    <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#1E1E1E] shadow-xl overflow-hidden backdrop-blur-md">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Toggle executive synthesis"
        className="w-full flex items-center justify-between p-5 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors focus:outline-none cursor-pointer border-b border-black/5 dark:border-white/5"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#2525A3]/15 flex items-center justify-center text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/25">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="text-left">
            <h3 className="font-headline font-bold text-black dark:text-[#ECECF1] text-base tracking-tight">
              Executive Synthesis &amp; Strategic Roadmap
            </h3>
            <p className="text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0]">
              Cross-domain intelligence synthesized by Supervisor Agent
            </p>
          </div>
        </div>

        <motion.div
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="w-8 h-8 rounded-lg bg-black/5 dark:bg-white/5 flex items-center justify-center text-[#737373] dark:text-[#8E8EA0]"
        >
          <ChevronDown className="w-4 h-4" />
        </motion.div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-6 text-black dark:text-[#ECECF1] prose prose-neutral dark:prose-invert prose-sm max-w-none font-sans leading-relaxed overflow-x-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

