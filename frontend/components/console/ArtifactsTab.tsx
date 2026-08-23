"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  FileCode,
  Image as ImageIcon,
  File,
  Download,
  ExternalLink,
  ChevronRight,
  ChevronDown,
  Loader2,
  FolderOpen,
} from "lucide-react";
import { listArtifacts, getArtifact, type ArtifactPart } from "@/lib/adk-client";

const iconBtn =
  "rounded-lg p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-black/5 dark:hover:bg-white/10 hover:text-black dark:hover:text-white cursor-pointer";

function iconFor(name: string) {
  if (/\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(name)) return ImageIcon;
  if (/\.(html?|xml|svg)$/i.test(name)) return FileCode;
  if (/\.(md|txt|json|ya?ml|csv|log|ya?ml)$/i.test(name)) return FileText;
  return File;
}

function normalizeB64(input: string): string {
  let b64 = input.includes(",") && /^data:/i.test(input)
    ? input.slice(input.indexOf(",") + 1)
    : input;
  b64 = b64.replace(/\s/g, "").replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4;
  if (pad) b64 += "=".repeat(4 - pad);
  return b64;
}

function safeAtob(b64: string): string {
  const norm = normalizeB64(b64);
  try {
    return decodeURIComponent(escape(atob(norm)));
  } catch {
    try {
      return atob(norm);
    } catch {
      return "";
    }
  }
}

function b64ToBlob(b64: string, mime: string): Blob {
  try {
    const bin = atob(normalizeB64(b64));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  } catch {
    return new Blob([b64], { type: mime });
  }
}

export function ArtifactsTab({ userId, sessionId }: { userId: string; sessionId: string | null }) {
  const [names, setNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId || !userId) {
      setNames([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listArtifacts(userId, sessionId)
      .then((n) => {
        if (!cancelled) setNames(n);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, sessionId]);

  if (!sessionId) return <Empty text="No active session key." />;
  if (loading && names.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs font-mono text-slate-500 dark:text-slate-400">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Scanning ADK artifact store…
      </div>
    );
  }
  if (names.length === 0) return <Empty text="No session artifacts generated yet." />;

  return (
    <div className="space-y-2.5 font-sans">
      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        SAVED ARTIFACTS ({names.length})
      </span>
      {names.map((n) => (
        <ArtifactCard key={n} userId={userId} sessionId={sessionId} name={n} />
      ))}
    </div>
  );
}

function ArtifactCard({
  userId,
  sessionId,
  name,
}: {
  userId: string;
  sessionId: string;
  name: string;
}) {
  const [open, setOpen] = useState(false);
  const [part, setPart] = useState<ArtifactPart | null>(null);
  const [busy, setBusy] = useState(false);
  const Icon = iconFor(name);

  const isHtml = /\.html?$/i.test(name);
  const isImage = /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(name);

  const ensureLoaded = async (): Promise<ArtifactPart | null> => {
    if (part) return part;
    setBusy(true);
    const p = await getArtifact(userId, sessionId, name);
    setPart(p);
    setBusy(false);
    return p;
  };

  const partToBlob = (p: ArtifactPart, fallbackMime: string): Blob => {
    const mime = p.inlineData?.mimeType ?? fallbackMime;
    return p.inlineData?.data
      ? b64ToBlob(p.inlineData.data, mime)
      : new Blob([p.text ?? ""], { type: mime });
  };

  const handleDownload = async () => {
    const p = await ensureLoaded();
    if (!p) return;
    const url = URL.createObjectURL(partToBlob(p, "application/octet-stream"));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleOpen = async () => {
    const p = await ensureLoaded();
    if (!p) return;
    const url = URL.createObjectURL(partToBlob(p, "text/html"));
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };

  const handleToggle = async () => {
    if (!open) await ensureLoaded();
    setOpen((o) => !o);
  };

  const mime = part?.inlineData?.mimeType ?? "";
  const decoded = part?.inlineData?.data ? safeAtob(part.inlineData.data) : part?.text ?? "";

  return (
    <div className="overflow-hidden rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.03] backdrop-blur-md shadow-xs">
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Icon className="h-4 w-4 shrink-0 text-[#2525A3] dark:text-[#A6C3EE]" />
        <span className="flex-1 truncate font-mono text-xs text-black dark:text-[#ECECF1] font-medium">{name}</span>
        {isHtml && (
          <button onClick={handleOpen} title="Open in new tab" className={iconBtn}>
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        )}
        <button onClick={handleDownload} title="Download artifact" className={iconBtn}>
          <Download className="h-3.5 w-3.5" />
        </button>
        {!isHtml && (
          <button onClick={handleToggle} title={open ? "Collapse" : "Preview"} className={iconBtn}>
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      {open && !isHtml && (
        <div className="border-t border-black/10 dark:border-white/10 p-3 bg-black/[0.03] dark:bg-black/40">
          {busy ? (
            <div className="flex items-center gap-2 py-3 text-xs font-mono text-slate-500 dark:text-slate-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#2525A3] dark:text-[#A6C3EE]" /> Loading payload…
            </div>
          ) : isImage && part?.inlineData?.data ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`data:${mime || "image/png"};base64,${normalizeB64(part.inlineData.data)}`}
              alt={name}
              className="max-w-full rounded-lg border border-black/10 dark:border-white/10"
            />
          ) : (
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-800 dark:text-slate-200 custom-scrollbar">
              {decoded || "(empty artifact)"}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex h-full min-h-40 items-center justify-center text-center">
      <p className="text-xs font-mono text-slate-500">{text}</p>
    </div>
  );
}

