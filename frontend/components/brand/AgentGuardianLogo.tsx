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
    <div className={`inline-flex items-center gap-2.5 shrink-0 group ${className}`}>
      <div
        className="relative flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-105"
        style={{ width: pixelSize, height: pixelSize }}
      >
        <Image
          src="/agent-guardian-logo.svg"
          alt="Agent Guardian Logo"
          width={pixelSize * 2}
          height={pixelSize * 2}
          priority={priority}
          className="w-full h-full object-contain select-none transition-all duration-300"
        />
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
