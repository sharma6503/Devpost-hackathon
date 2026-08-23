"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Copy,
  Check,
  Download,
  Code2,
  Terminal,
  Clock,
  Layers,
  Wrench,
  FileCode,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { AdkEvent } from "@/types/adk";

export interface EventInspectorModalProps {
  isOpen: boolean;
  event: AdkEvent | null;
  onClose: () => void;
}

export function EventInspectorModal({
  isOpen,
  event,
  onClose,
}: EventInspectorModalProps) {
  const [copied, setCopied] = useState(false);
  const [activeView, setActiveView] = useState<"json" | "structured">("json");

  // Reset copied state when event changes
  useEffect(() => {
    setCopied(false);
  }, [event]);

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !event) return null;

  const jsonString = JSON.stringify(event, null, 2);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API fails
      const el = document.createElement("textarea");
      el.value = jsonString;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([jsonString], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `adk-event-${event.author || "unknown"}-${event.id || Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const authorName = (event.author || "system")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  const formattedTime = event.timestamp
    ? new Date(
        typeof event.timestamp === "number" && event.timestamp < 10000000000
          ? event.timestamp * 1000
          : event.timestamp
      ).toLocaleString()
    : "Live Execution";

  const functionCalls = (event.content?.parts || [])
    .filter((p) => Boolean(p.functionCall))
    .map((p) => p.functionCall!);

  const functionResponses = (event.content?.parts || [])
    .filter((p) => Boolean(p.functionResponse))
    .map((p) => p.functionResponse!);

  const textParts = (event.content?.parts || [])
    .filter((p) => Boolean(p.text))
    .map((p) => p.text!);

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[70] flex items-center justify-center p-3 sm:p-6 bg-black/60 backdrop-blur-sm animate-fade-in">
        {/* Backdrop click to close */}
        <div className="fixed inset-0" onClick={onClose} />

        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.18 }}
          className="relative w-full max-w-4xl bg-white dark:bg-[#1E1E1E] rounded-2xl shadow-2xl border border-black/10 dark:border-white/10 overflow-hidden flex flex-col max-h-[88vh] z-10"
        >
          {/* Modal Header */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-black/10 dark:border-white/10 bg-[#F9F9F9] dark:bg-[#252525] select-none">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#2525A3] text-white shadow-xs">
                <Code2 className="h-4 w-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-black dark:text-[#ECECF1]">
                    Raw ADK Event Inspector
                  </h3>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/25">
                    {authorName}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0] mt-0.5">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formattedTime}
                  </span>
                  {event.id && (
                    <>
                      <span>•</span>
                      <span className="truncate max-w-[160px] sm:max-w-[240px]">
                        ID: {event.id}
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Actions Bar */}
            <div className="flex items-center gap-1.5 ml-auto">
              {/* Toggle view mode */}
              <div className="flex items-center p-0.5 rounded-lg bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 mr-1 text-[11px] font-mono">
                <button
                  onClick={() => setActiveView("json")}
                  className={`px-2 py-1 rounded-md transition-colors cursor-pointer ${
                    activeView === "json"
                      ? "bg-white dark:bg-[#333] text-black dark:text-white font-semibold shadow-2xs"
                      : "text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white"
                  }`}
                >
                  Raw JSON
                </button>
                <button
                  onClick={() => setActiveView("structured")}
                  className={`px-2 py-1 rounded-md transition-colors cursor-pointer ${
                    activeView === "structured"
                      ? "bg-white dark:bg-[#333] text-black dark:text-white font-semibold shadow-2xs"
                      : "text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white"
                  }`}
                >
                  Structured
                </button>
              </div>

              {/* Copy Button */}
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-mono text-black dark:text-[#ECECF1] transition-colors cursor-pointer border border-black/5 dark:border-white/5"
                title="Copy full JSON payload"
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                    <span className="text-emerald-500 font-semibold">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                    <span>Copy</span>
                  </>
                )}
              </button>

              {/* Download Button */}
              <button
                onClick={handleDownload}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-mono text-black dark:text-[#ECECF1] transition-colors cursor-pointer border border-black/5 dark:border-white/5"
                title="Download JSON file"
              >
                <Download className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                <span className="hidden sm:inline">Download</span>
              </button>

              {/* Close Button */}
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-white transition-colors cursor-pointer"
                title="Close (Esc)"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Modal Content Body */}
          <div className="p-4 sm:p-5 overflow-y-auto custom-scrollbar flex-1 space-y-4">
            {activeView === "json" ? (
              <div className="relative rounded-xl border border-black/10 dark:border-white/10 bg-[#0E1F3D]/5 dark:bg-[#121212] p-4 font-mono text-xs overflow-x-auto custom-scrollbar">
                <pre className="text-[#0D0D0D] dark:text-[#E2E8F0] text-[11.5px] leading-relaxed select-text font-mono">
                  {jsonString}
                </pre>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Event Summary Overview */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                  <div className="p-3 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
                    <span className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">
                      Author
                    </span>
                    <p className="font-semibold text-xs text-black dark:text-white mt-0.5 truncate">
                      {authorName}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
                    <span className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">
                      Role
                    </span>
                    <p className="font-semibold text-xs text-black dark:text-white mt-0.5 uppercase font-mono">
                      {event.content?.role || "model"}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
                    <span className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">
                      Turn Complete
                    </span>
                    <p className="font-semibold text-xs text-black dark:text-white mt-0.5 font-mono">
                      {event.turnComplete ? "true" : "false"}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/5">
                    <span className="text-[10px] uppercase font-mono text-[#737373] dark:text-[#8E8EA0]">
                      Tool Calls
                    </span>
                    <p className="font-semibold text-xs text-black dark:text-white mt-0.5 font-mono">
                      {functionCalls.length + functionResponses.length}
                    </p>
                  </div>
                </div>

                {/* Error Banner if any */}
                {event.errorMessage && (
                  <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/30 flex items-start gap-2.5 text-red-600 dark:text-red-400">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-xs font-semibold">
                        Event Error: {event.errorCode || "RUNTIME_EXCEPTION"}
                      </h4>
                      <p className="text-xs font-mono mt-0.5 leading-relaxed">
                        {event.errorMessage}
                      </p>
                    </div>
                  </div>
                )}

                {/* Function Calls */}
                {functionCalls.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0] flex items-center gap-1.5">
                      <Wrench className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                      Function Invocations ({functionCalls.length})
                    </h4>
                    <div className="space-y-2">
                      {functionCalls.map((fc, i) => (
                        <div
                          key={i}
                          className="p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.01] dark:bg-white/[0.02] space-y-1.5"
                        >
                          <div className="flex items-center justify-between font-mono text-xs">
                            <span className="font-bold text-[#2525A3] dark:text-[#A6C3EE]">
                              {fc.name}()
                            </span>
                            <span className="text-[10px] text-[#737373] dark:text-[#8E8EA0]">
                              Call ID: {fc.id}
                            </span>
                          </div>
                          {fc.args && Object.keys(fc.args).length > 0 && (
                            <pre className="p-2 rounded-lg bg-black/[0.03] dark:bg-black/30 font-mono text-[11px] overflow-x-auto">
                              {JSON.stringify(fc.args, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Function Responses */}
                {functionResponses.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0] flex items-center gap-1.5">
                      <Terminal className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                      Function Execution Responses ({functionResponses.length})
                    </h4>
                    <div className="space-y-2">
                      {functionResponses.map((fr, i) => (
                        <div
                          key={i}
                          className="p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.01] dark:bg-white/[0.02] space-y-1.5"
                        >
                          <div className="flex items-center justify-between font-mono text-xs">
                            <span className="font-bold text-black dark:text-white">
                              {fr.name} response
                            </span>
                            <span className="text-[10px] text-[#737373] dark:text-[#8E8EA0]">
                              Call ID: {fr.id}
                            </span>
                          </div>
                          <pre className="p-2 rounded-lg bg-black/[0.03] dark:bg-black/30 font-mono text-[11px] overflow-x-auto max-h-48 custom-scrollbar">
                            {JSON.stringify(fr.response, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Text Content */}
                {textParts.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0] flex items-center gap-1.5">
                      <FileCode className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                      Text Payload ({textParts.length} Parts)
                    </h4>
                    <div className="space-y-2">
                      {textParts.map((txt, i) => (
                        <div
                          key={i}
                          className="p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.01] dark:bg-white/[0.02] text-xs font-mono text-black dark:text-[#ECECF1] whitespace-pre-wrap leading-relaxed max-h-56 overflow-y-auto custom-scrollbar"
                        >
                          {txt}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* State / Actions Delta */}
                {event.actions && Object.keys(event.actions).length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-mono font-bold uppercase text-[#737373] dark:text-[#8E8EA0] flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
                      Session State & Artifact Actions Delta
                    </h4>
                    <div className="p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.01] dark:bg-white/[0.02] font-mono text-xs overflow-x-auto max-h-56 custom-scrollbar">
                      <pre className="text-[11px] leading-relaxed">
                        {JSON.stringify(event.actions, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer Bar */}
          <div className="flex items-center justify-between px-5 py-2.5 border-t border-black/10 dark:border-white/10 bg-[#F9F9F9] dark:bg-[#252525] text-[11px] font-mono text-[#737373] dark:text-[#8E8EA0] select-none">
            <div className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE]" />
              <span>Google ADK Telemetry Runtime</span>
            </div>
            <button
              onClick={onClose}
              className="px-3 py-1 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-sans text-black dark:text-white transition-colors cursor-pointer"
            >
              Close
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
