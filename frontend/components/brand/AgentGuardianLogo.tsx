"use client";

import React from "react";
import Image from "next/image";

interface AgentGuardianLogoProps {
  size?: number | "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "hero";
  className?: string;
  showText?: boolean;
  textClassName?: string;
  withGlow?: boolean;
  priority?: boolean;
}

const SIZE_MAP: Record<string, number> = {
  xs: 18,
  sm: 24,
  md: 32,
  lg: 40,
  xl: 48,
  "2xl": 64,
  hero: 96,
};

export function AgentGuardianLogo({
  size = "md",
  className = "",
  showText = false,
  textClassName = "",
  withGlow = false,
  priority = false,
}: AgentGuardianLogoProps) {
  const pixelSize = typeof size === "number" ? size : (SIZE_MAP[size] ?? 32);

  return (
    <div className={`inline-flex items-center gap-2.5 shrink-0 ${className}`}>
      <div
        className={`relative flex items-center justify-center rounded-xl overflow-hidden shrink-0 ${
          withGlow ? "shadow-lg shadow-[#2525A3]/25" : ""
        }`}
        style={{ width: pixelSize, height: pixelSize }}
      >
        <Image
          src="/agent-guardian-logo.svg"
          alt="Agent Guardian Logo"
          width={pixelSize * 2}
          height={pixelSize * 2}
          priority={priority}
          className="w-full h-full object-contain rounded-xl select-none"
        />
        {withGlow && (
          <div className="absolute inset-0 rounded-xl bg-[#2525A3]/20 animate-pulse pointer-events-none" />
        )}
      </div>

      {showText && (
        <span
          className={`font-semibold tracking-tight text-black dark:text-[#ECECF1] select-none ${
            textClassName || "text-sm md:text-base"
          }`}
        >
          Agent Guardian
        </span>
      )}
    </div>
  );
}
