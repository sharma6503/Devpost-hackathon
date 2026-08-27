import React, { useState, useRef, useEffect } from "react";
import {
  SlidersHorizontal,
  PanelLeft,
  PanelLeftClose,
  PanelTop,
  PanelTopClose,
  ChevronUp,
  Sun,
  Moon,
  ShieldCheck,
  FolderArchive,
  GitBranch,
  Search,
  ChevronDown,
  Bot,
  Check,
  Plus,
  Share2,
} from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";

export interface SwarmModel {
  id: string;
  name: string;
  badge?: string;
  description?: string;
}

export const SWARM_MODELS: SwarmModel[] = [
  {
    id: "agent_guardian",
    name: "Agent Guardian",
    description: "Autonomous Agent Review & Auditing System.",
  },
];

export interface GuardianHeaderProps {
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
  headerVisible?: boolean;
  onToggleHeader?: () => void;
  activeSessionId?: string;
  activeRepo?: string;
  agentTitle?: string;
  availableApps?: string[];
  activeAppName?: string;
  onSelectApp?: (appName: string) => void;
  selectedModel?: string;
  onSelectModel?: (modelId: string) => void;
  onToggleInspector?: () => void;
  onOpenSearch?: () => void;
  onOpenShare?: () => void;
  inspectorOpen?: boolean;
  isRunning?: boolean;
}

/**
 * Extracts a human-friendly repository, archive name, or session summary
 * while stripping out internal injected prompt notes.
 */
function formatHeaderTarget(target?: string, sessionId?: string): string {
  if (!target) {
    return sessionId ? `Session ${sessionId.slice(0, 8)}` : "Ready";
  }

  // Strip system notes like [System Note: User attached a ZIP file...]
  let cleaned = target.replace(/\[System Note:[\s\S]*?\]/gi, "").trim();

  // Match GitHub repository URL: https://github.com/owner/repo
  const ghMatch = cleaned.match(/https?:\/\/github\.com\/([a-zA-Z0-9_.\-]+(?:\/[a-zA-Z0-9_.\-]+)?)/i);
  if (ghMatch) {
    return ghMatch[1].replace(/\.git$/i, "");
  }

  // Match attached file note: 📎 Attached: `filename.zip`
  const attachedMatch = cleaned.match(/📎\s*(?:Attached:)?\s*`?([a-zA-Z0-9_.\- ]+\.[a-zA-Z0-9]+)`?/i);
  if (attachedMatch) {
    return attachedMatch[1];
  }

  // Match standalone zip/tar archive reference
  const zipMatch = cleaned.match(/([a-zA-Z0-9_\-.]+\.(?:zip|tar\.gz|tar))/i);
  if (zipMatch) {
    return zipMatch[1];
  }

  // Clean first sentence / user text
  const firstLine = cleaned.split("\n")[0].trim();
  if (firstLine.length > 32) {
    return firstLine.slice(0, 32) + "…";
  }
  return firstLine || (sessionId ? `Session ${sessionId.slice(0, 8)}` : "Active");
}

export function GuardianHeader({
  isSidebarOpen,
  onToggleSidebar,
  headerVisible = true,
  onToggleHeader,
  activeSessionId,
  activeRepo,
  agentTitle = "Agent Guardian",
  availableApps = ["agent_guardian"],
  activeAppName = "agent_guardian",
  onSelectApp,
  onToggleInspector,
  onOpenSearch,
  onOpenShare,
  inspectorOpen,
  isRunning,
}: GuardianHeaderProps) {
  const { toggleTheme, isDark } = useTheme();
  const [appMenuOpen, setAppMenuOpen] = useState(false);
  const [customAppInput, setCustomAppInput] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const displayTarget = formatHeaderTarget(activeRepo, activeSessionId);
  const isGithub = Boolean(activeRepo && (activeRepo.includes("github.com") || activeRepo.includes("git@")));
  const isZip = Boolean(activeRepo && (activeRepo.endsWith(".zip") || activeRepo.includes("Attached:")));

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setAppMenuOpen(false);
        setShowCustomInput(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleCustomAppSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = customAppInput.trim();
    if (clean && onSelectApp) {
      onSelectApp(clean);
      setCustomAppInput("");
      setShowCustomInput(false);
      setAppMenuOpen(false);
    }
  };

  const formatAppName = (name: string) => {
    if (name === "agent_guardian") return "Agent Guardian";
    return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between px-3 md:px-5 py-2.5 bg-white/95 dark:bg-[#212121]/95 backdrop-blur-md border-b border-black/10 dark:border-white/10 select-none transition-colors duration-200">
      {/* ─── Left: Brand Identity & App Selector ─── */}
      <div className="flex items-center gap-2 md:gap-2.5 min-w-0 relative" ref={menuRef}>
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="md:hidden p-1.5 -ml-1 rounded-lg text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer shrink-0"
            title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
            aria-label="Toggle sidebar"
          >
            <PanelLeft className="h-4 w-4" />
          </button>
        )}

        <div className="flex items-center gap-2 min-w-0">
          <AgentGuardianLogo size={28} priority />
          
          <button
            onClick={() => setAppMenuOpen(!appMenuOpen)}
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer text-left group"
            title="Select ADK Agent / App"
          >
            <div className="flex flex-col min-w-0">
              <span className="text-black dark:text-[#ECECF1] font-semibold text-sm md:text-base tracking-tight truncate flex items-center gap-1">
                {formatAppName(activeAppName)}
                <ChevronDown className="h-3.5 w-3.5 text-[#737373] dark:text-[#8E8EA0] group-hover:text-black dark:group-hover:text-white transition-colors" />
              </span>
            </div>
          </button>

          <span className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] border border-[#2525A3]/20 select-none">
            <ShieldCheck className="h-2.5 w-2.5" />
            Google ADK
          </span>
        </div>

        {/* Dynamic ADK App Selection Dropdown */}
        {appMenuOpen && (
          <div className="absolute top-full left-8 mt-1.5 w-64 p-1.5 rounded-2xl bg-white dark:bg-[#2F2F2F] border border-black/10 dark:border-white/10 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-150">
            <div className="px-2.5 py-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-[#737373] dark:text-[#8E8EA0] border-b border-black/5 dark:border-white/5 mb-1">
              Active ADK Agents
            </div>
            <div className="space-y-0.5 max-h-48 overflow-y-auto custom-scrollbar">
              {availableApps.map((app) => {
                const isCurrent = app === activeAppName;
                return (
                  <button
                    key={app}
                    onClick={() => {
                      onSelectApp?.(app);
                      setAppMenuOpen(false);
                    }}
                    className={`flex items-center justify-between w-full px-2.5 py-2 rounded-xl text-xs transition-colors cursor-pointer text-left ${
                      isCurrent
                        ? "bg-[#2525A3]/10 text-[#2525A3] dark:text-[#A6C3EE] font-medium"
                        : "text-black dark:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <Bot className={`h-3.5 w-3.5 ${isCurrent ? "text-[#2525A3] dark:text-[#A6C3EE]" : "text-[#737373] dark:text-[#8E8EA0]"}`} />
                      <span className="truncate">{formatAppName(app)}</span>
                    </div>
                    {isCurrent && <Check className="h-3.5 w-3.5 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />}
                  </button>
                );
              })}
            </div>

            {/* Custom App Connect Input */}
            <div className="border-t border-black/5 dark:border-white/5 pt-1 mt-1">
              {showCustomInput ? (
                <form onSubmit={handleCustomAppSubmit} className="p-1">
                  <input
                    type="text"
                    value={customAppInput}
                    onChange={(e) => setCustomAppInput(e.target.value)}
                    placeholder="e.g. weather_agent"
                    autoFocus
                    className="w-full px-2.5 py-1.5 rounded-lg border border-black/15 dark:border-white/15 bg-black/5 dark:bg-black/20 text-black dark:text-[#ECECF1] text-xs font-mono focus:outline-hidden focus:border-[#2525A3]"
                  />
                  <div className="flex items-center justify-end gap-1.5 mt-1.5">
                    <button
                      type="button"
                      onClick={() => setShowCustomInput(false)}
                      className="px-2 py-1 text-[11px] text-[#737373] hover:text-black dark:hover:text-white cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={!customAppInput.trim()}
                      className="px-2.5 py-1 bg-[#2525A3] hover:bg-[#1E1E82] text-white rounded text-[11px] font-medium disabled:opacity-40 cursor-pointer"
                    >
                      Connect
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  onClick={() => setShowCustomInput(true)}
                  className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded-xl text-xs text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Connect Custom ADK App...</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ─── Center: Active Target / Repository Pill ─── */}
      {activeSessionId && (
        <div className="hidden md:flex items-center justify-center max-w-[340px] px-2 min-w-0">
          <div
            className="flex items-center gap-2 px-3 py-1 rounded-full bg-black/[0.04] dark:bg-white/[0.05] border border-black/10 dark:border-white/10 text-xs text-[#737373] dark:text-[#8E8EA0] shadow-2xs min-w-0"
            title={activeRepo || activeSessionId}
          >
            <span
              className={`h-2 w-2 rounded-full shrink-0 ${
                isRunning ? "bg-[#2525A3] animate-pulse" : "bg-[#2525A3]"
              }`}
            />
            {isGithub ? (
              <GitBranch className="h-3 w-3 text-[#2525A3] dark:text-[#A6C3EE] shrink-0" />
            ) : isZip ? (
              <FolderArchive className="h-3 w-3 text-[#2525A3] shrink-0" />
            ) : null}
            <span className="font-mono text-[11px] text-black dark:text-[#ECECF1] truncate max-w-[240px]">
              {displayTarget}
            </span>
          </div>
        </div>
      )}

      {/* ─── Right: Actions Toolbar (Theme, Export, Console) ─── */}
      <div className="flex items-center gap-1.5 md:gap-2 shrink-0">
        {/* Live Status Badge on mobile */}
        {isRunning && (
          <span className="flex md:hidden items-center gap-1 text-[11px] font-mono text-[#2525A3] dark:text-[#A6C3EE] font-medium px-2 py-0.5 rounded-full bg-[#2525A3]/10">
            <span className="h-1.5 w-1.5 rounded-full bg-[#2525A3] animate-pulse" />
            Running
          </span>
        )}

        {/* Quick Audit Search Trigger */}
        {onOpenSearch && (
          <button
            onClick={onOpenSearch}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/20 hover:bg-black/5 dark:hover:bg-white/5 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] text-xs font-medium transition-all cursor-pointer"
            title="Search audits (Ctrl+K / Cmd+K)"
            aria-label="Search audits"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden lg:inline-flex items-center px-1 py-0.2 rounded text-[10px] font-mono bg-black/5 dark:bg-white/10 text-[#737373] dark:text-[#8E8EA0]">
              ⌘K
            </kbd>
          </button>
        )}

        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/20 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-all cursor-pointer"
          title={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
          aria-label="Toggle Light/Dark Theme"
        >
          {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-700" />}
        </button>

        {/* Export & Share Modal Trigger */}
        {onOpenShare && (
          <button
            onClick={onOpenShare}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/20 hover:bg-black/5 dark:hover:bg-white/5 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] text-xs font-medium transition-all cursor-pointer"
            title="Export & Share Audit Report"
            aria-label="Export Audit"
          >
            <Share2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Export</span>
          </button>
        )}

        {/* Mission Control Console Toggle */}
        {onToggleInspector && (
          <button
            onClick={onToggleInspector}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors cursor-pointer text-xs font-medium ${
              inspectorOpen
                ? "bg-[#2525A3] text-white border-[#2525A3]"
                : "border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/20 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5"
            }`}
            title="Toggle Mission Control Telemetry Console"
            aria-label="Toggle Console"
          >
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden md:inline">Console</span>
          </button>
        )}

        {/* Top-Right Toggle Full Header & Ribbon Section */}
        {onToggleHeader && (
          <button
            onClick={onToggleHeader}
            className="p-2 rounded-lg border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/20 text-[#737373] dark:text-[#8E8EA0] hover:text-black dark:hover:text-[#ECECF1] hover:bg-black/5 dark:hover:bg-white/5 transition-all cursor-pointer shadow-2xs group"
            title="Hide Header (Alt+H)"
            aria-label="Hide Header"
          >
            <ChevronUp className="h-4 w-4 text-[#737373] dark:text-[#8E8EA0] group-hover:text-black dark:group-hover:text-white transition-colors" />
          </button>
        )}
      </div>
    </header>
  );
}
