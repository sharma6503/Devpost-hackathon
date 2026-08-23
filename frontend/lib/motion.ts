import type { Variants, Transition } from "framer-motion";

// ─── Spring presets ────────────────────────────────────────────────────────
export const spring = {
  /** Cards, pills, badges — tight and responsive */
  snappy: { type: "spring" as const, stiffness: 260, damping: 22 },
  /** Page-level elements — natural feel */
  smooth: { type: "spring" as const, stiffness: 200, damping: 20 },
  /** Large panels, drawers — unhurried */
  slow:   { type: "spring" as const, stiffness: 120, damping: 18 },
  /** Count-up motion values — useSpring config (no type key) */
  counter: { stiffness: 80, damping: 20 },
} as const;

// ─── Durations (for non-spring transitions) ───────────────────────────────
export const dur = {
  fast:   0.15,
  normal: 0.22,
  slow:   0.35,
} as const;

// ─── Stagger containers ────────────────────────────────────────────────────
export const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};

export const staggerFast: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04 } },
};

// ─── Standard item variants ────────────────────────────────────────────────
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show:   { opacity: 1, y: 0,  transition: spring.snappy },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show:   { opacity: 1, transition: spring.smooth },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  show:   { opacity: 1, scale: 1,  transition: spring.snappy },
};

export const slideRight: Variants = {
  hidden: { opacity: 0, x: -12 },
  show:   { opacity: 1, x: 0,   transition: spring.smooth },
};

// ─── Page / tab transitions ────────────────────────────────────────────────
export const pageTransition = {
  initial:    { opacity: 0, y: 8 },
  animate:    { opacity: 1, y: 0 },
  exit:       { opacity: 0, y: -8 },
  transition: { duration: dur.normal } satisfies Transition,
};

// ─── Height collapse (AnimatePresence panels) ─────────────────────────────
export const collapseTransition: Transition = {
  duration: dur.normal,
  ease: "easeInOut",
};
