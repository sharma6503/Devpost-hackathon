"use client";

import { useState } from "react";
import {
  Share2,
  Copy,
  Check,
  Download,
  FileText,
  FileJson,
  X,
  ExternalLink,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

export interface ExportShareModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string;
  repoUrl?: string;
  markdownContent?: string;
  telemetryJson?: any;
}

export function ExportShareModal({
  isOpen,
  onClose,
  sessionId = "demo-session",
  repoUrl = "",
  markdownContent = "",
  telemetryJson = {},
}: ExportShareModalProps) {
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedMd, setCopiedMd] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);
  const { theme } = useTheme();

  if (!isOpen) return null;

  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/?session=${encodeURIComponent(sessionId)}`
    : `https://agentguardian.dev/?session=${encodeURIComponent(sessionId)}`;

  const handleCopyLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    const text = markdownContent || `# Agent Guardian Audit Dossier\n\nSession: ${sessionId}\nRepository: ${repoUrl}\n\nGenerated with Agent Guardian Swarm.`;
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agent-guardian-dossier-${sessionId.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyMarkdown = () => {
    const text = markdownContent || `# Agent Guardian Audit Dossier\n\nSession: ${sessionId}\nRepository: ${repoUrl}`;
    navigator.clipboard.writeText(text);
    setCopiedMd(true);
    setTimeout(() => setCopiedMd(false), 2000);
  };

  const handleDownloadJson = () => {
    const text = JSON.stringify(telemetryJson, null, 2);
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agent-guardian-telemetry-${sessionId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(telemetryJson, null, 2));
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in font-sans">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-modal-title"
        className="relative flex flex-col w-full max-w-lg rounded-2xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#212121] shadow-2xl overflow-hidden animate-scale-in"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/10 dark:border-white/10 bg-[#F9F9F9] dark:bg-[#171717] select-none">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#2525A3] text-white shadow-sm">
              <Share2 className="h-4 w-4" />
            </div>
            <div>
              <h3 id="share-modal-title" className="text-sm font-semibold text-black dark:text-[#ECECF1]">
                Share & Export Audit
              </h3>
              <p className="text-[11px] text-[#737373] dark:text-[#8E8EA0] font-mono">
                Session: {sessionId.slice(0, 16)}...
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#737373] hover:text-black dark:text-[#8E8EA0] dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
            aria-label="Close modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5">
          {/* Share Link */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-black dark:text-[#ECECF1] flex items-center gap-1.5">
              <span>Direct Link to Audit Workspace</span>
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={shareUrl}
                className="flex-1 px-3 py-2 text-xs rounded-xl bg-black/5 dark:bg-black/20 border border-black/10 dark:border-white/10 text-[#737373] dark:text-[#8E8EA0] font-mono focus:outline-hidden"
              />
              <button
                onClick={handleCopyLink}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-xl bg-[#2525A3] hover:bg-[#1E1E82] text-white transition-all shadow-sm shrink-0 cursor-pointer"
              >
                {copiedLink ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copiedLink ? "Copied" : "Copy"}</span>
              </button>
            </div>
          </div>

          {/* Export Options */}
          <div className="space-y-3 pt-2 border-t border-black/5 dark:border-white/5">
            <div className="text-xs font-semibold text-black dark:text-[#ECECF1]">
              Export Formats
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Markdown Export */}
              <div className="p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.02] flex flex-col justify-between space-y-2">
                <div className="flex items-start gap-2.5">
                  <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500 shrink-0">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-black dark:text-[#ECECF1]">
                      Markdown Dossier
                    </div>
                    <div className="text-[11px] text-[#737373] dark:text-[#8E8EA0] truncate">
                      Executive findings & report
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 pt-1">
                  <button
                    onClick={handleDownloadMarkdown}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-[11px] font-medium text-black dark:text-[#ECECF1] transition-colors cursor-pointer"
                  >
                    <Download className="h-3 w-3" />
                    <span>Download</span>
                  </button>
                  <button
                    onClick={handleCopyMarkdown}
                    className="p-1.5 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-black dark:text-[#ECECF1] transition-colors cursor-pointer"
                    title="Copy Markdown"
                  >
                    {copiedMd ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                  </button>
                </div>
              </div>

              {/* JSON Telemetry Export */}
              <div className="p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.02] flex flex-col justify-between space-y-2">
                <div className="flex items-start gap-2.5">
                  <div className="p-2 rounded-lg bg-purple-500/10 text-purple-500 shrink-0">
                    <FileJson className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-black dark:text-[#ECECF1]">
                      JSON Telemetry
                    </div>
                    <div className="text-[11px] text-[#737373] dark:text-[#8E8EA0] truncate">
                      Full trace & state metrics
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 pt-1">
                  <button
                    onClick={handleDownloadJson}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-[11px] font-medium text-black dark:text-[#ECECF1] transition-colors cursor-pointer"
                  >
                    <Download className="h-3 w-3" />
                    <span>Download</span>
                  </button>
                  <button
                    onClick={handleCopyJson}
                    className="p-1.5 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-black dark:text-[#ECECF1] transition-colors cursor-pointer"
                    title="Copy JSON"
                  >
                    {copiedJson ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Security note */}
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[#2525A3]/5 border border-[#2525A3]/15 text-[11px] text-[#2525A3] dark:text-[#A6C3EE]">
            <ShieldCheck className="h-4 w-4 shrink-0" />
            <span>Audit traces and credentials are strictly sanitized prior to export.</span>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-[#F9F9F9] dark:bg-[#171717] border-t border-black/10 dark:border-white/10 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-black dark:text-[#ECECF1] transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
