"use client";
import { useState, useCallback } from "react";

export function useLogPopout() {
  const [isPopped, setIsPopped] = useState(false);
  const toggle = useCallback(() => setIsPopped((p) => !p), []);
  return { isPopped, toggle };
}
