"use client";
import { useEffect, useRef } from "react";

export function useBrowserNotification(isComplete: boolean) {
  const firedRef = useRef(false);

  // Request permission early (non-blocking)
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      Notification.requestPermission().catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (!isComplete || firedRef.current) return;
    firedRef.current = true;
    if (
      typeof window !== "undefined" &&
      "Notification" in window &&
      Notification.permission === "granted"
    ) {
      try {
        const n = new Notification("Agent Guardian — Review Complete", {
          body: "Your code audit is ready. Click to view the results.",
          icon: "/favicon.ico",
        });
        // Auto-close after 8 s
        setTimeout(() => n.close(), 8000);
      } catch { /* Safari may still throw */ }
    }
  }, [isComplete]);
}
