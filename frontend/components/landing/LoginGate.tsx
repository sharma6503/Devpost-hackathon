"use client";

import { useState } from "react";
import { User, Lock, Loader2, Sparkles, Building2, Globe } from "lucide-react";
import { AgentGuardianLogo } from "@/components/brand/AgentGuardianLogo";
import type { UserProfile } from "@/lib/session";

interface LoginGateProps {
  onSuccess: (profile: UserProfile) => void;
}

export function LoginGate({ onSuccess }: LoginGateProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Please enter your username and password");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail || data?.error || "Invalid credentials. Please verify username and password.");
        return;
      }
      onSuccess(
        data.profile || {
          userId: data.userId || username.trim(),
          department: data.department || "Security Engineering",
          country: data.country || "US",
        }
      );
    } catch {
      setError("Unable to connect to authentication server. Please check backend status.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md px-4 font-sans select-none animate-fade-in">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-7 shadow-2xl backdrop-blur-xl animate-scale-in text-[var(--color-text-primary)]"
      >
        <div className="text-center flex flex-col items-center">
          <AgentGuardianLogo size={48} priority className="mx-auto" />
          <h1 className="mt-3.5 text-lg font-headline font-semibold text-[var(--color-text-primary)] tracking-tight">
            Agent Guardian
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] font-sans mt-0.5">
            Sign In
          </p>
        </div>

        <div className="space-y-1.5 pt-2">
          <label
            htmlFor="ag-username"
            className="text-[11px] font-mono font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]"
          >
            Username
          </label>
          <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2.5 focus-within:border-[#2525A3] focus-within:ring-1 focus-within:ring-[#2525A3]/30 transition-all">
            <User className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
            <input
              id="ag-username"
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-transparent text-xs font-sans text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] outline-none"
              placeholder="e.g. operator"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="ag-password"
            className="text-[11px] font-mono font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]"
          >
            Password
          </label>
          <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2.5 focus-within:border-[#2525A3] focus-within:ring-1 focus-within:ring-[#2525A3]/30 transition-all">
            <Lock className="h-4 w-4 text-[#2525A3] dark:text-[#A6C3EE]" />
            <input
              id="ag-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-transparent text-xs font-sans text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] outline-none"
              placeholder="••••••••"
            />
          </div>
        </div>

        {error && (
          <p className="text-xs text-red-500 font-sans text-center pt-1 font-medium">{error}</p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#2525A3] hover:bg-[#1E1E88] active:scale-[0.98] py-2.5 text-xs font-sans font-semibold tracking-wide text-white shadow-md shadow-[#2525A3]/20 disabled:opacity-50 transition-all cursor-pointer mt-3"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-white" />
          ) : (
            "Authenticate & Launch"
          )}
        </button>
      </form>
    </div>
  );
}
