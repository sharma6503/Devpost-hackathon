"use client";

import { useCallback, useReducer, useRef } from "react";
import { runSse, getOrCreateSession } from "@/lib/adk-client";
import {
  applyEvent,
  buildInitialPhases,
  deepMergeState,
  finalizePhases,
  isDuplicateLog,
  toMillis,
} from "@/lib/event-parser";
import type {
  AdkEvent,
  LogEntry,
  PipelinePhase,
  ReviewState,
} from "@/types/adk";

interface ReviewHookState {
  phases: PipelinePhase[];
  activeAgent: string | null;
  /** Finalized log entries — only complete (non-partial) responses */
  log: LogEntry[];
  /** The chunk currently being streamed (partial=true). Shown as a live preview. */
  liveEntry: LogEntry | null;
  sessionState: Partial<ReviewState>;
  isComplete: boolean;
  isRunning: boolean;
  error: string | null;
  elapsedMs: number;
  /** True when review artifacts are present (synthesis/report/metrics). */
  producedReview: boolean;
}

/** Carry-over context when continuing an existing session (follow-up message):
 *  the prior conversation, pipeline phases, and session state are preserved
 *  instead of being wiped for a fresh run. */
export interface ReviewSeed {
  log: LogEntry[];
  phases: PipelinePhase[];
  sessionState: Partial<ReviewState>;
}

type Action =
  | { type: "START"; seed?: ReviewSeed }
  | { type: "RESET" }
  | { type: "USER_MESSAGE"; text: string }
  | { type: "EVENT"; event: AdkEvent }
  | { type: "LIVE"; entry: LogEntry | null }
  | { type: "TICK"; elapsedMs: number }
  | { type: "COMPLETE" }
  | { type: "ERROR"; message: string };

function reducer(state: ReviewHookState, action: Action): ReviewHookState {
  switch (action.type) {
    case "START": {
      const seedState = action.seed?.sessionState ?? {};
      const hasPriorReview = Boolean(
        seedState.synthesis_result &&
        seedState.synthesis_result !== "Not provided or skipped." &&
        !seedState.synthesis_result.startsWith("[INGESTION_FAILED]")
      );
      return {
        ...state,
        isRunning: true,
        error: null,
        phases: action.seed?.phases?.length ? action.seed.phases : buildInitialPhases(),
        log: action.seed?.log ?? [],
        liveEntry: null,
        sessionState: seedState,
        isComplete: false,
        activeAgent: null,
        elapsedMs: 0,
        producedReview: hasPriorReview,
      };
    }

    case "RESET":
      return {
        ...initialState,
        phases: buildInitialPhases(),
      };

    case "USER_MESSAGE":
      // Optimistically append the user's message (right-aligned in the chat). ADK does
      // not echo the user input back through run_sse, so we add it ourselves.
      return {
        ...state,
        log: [
          ...state.log,
          {
            id: `user_${Date.now()}`,
            author: "user",
            text: action.text,
            isPartial: false,
            timestamp: Date.now(),
            type: "text",
          },
        ],
      };

    case "LIVE":
      // Update the live preview without touching the finalized log
      return { ...state, liveEntry: action.entry };

    case "EVENT": {
      // Per-event updates only — completion is decided by stream close (COMPLETE),
      // never inferred from a single event.
      const { phases, activeAgent, newLogEntry, stateDelta } =
        applyEvent(state.phases, action.event, state.activeAgent);

      // Finalize the log: append new entry (skipping back-to-back duplicates), clear
      // the live preview.
      const log =
        newLogEntry && !isDuplicateLog(state.log[state.log.length - 1], newLogEntry)
          ? [...state.log.slice(-299), newLogEntry]
          : state.log;

      const sessionState = Object.keys(stateDelta).length
        ? deepMergeState(state.sessionState, stateDelta as Partial<ReviewState>)
        : state.sessionState;

      // Review-pipeline runs write these keys via state deltas; chat turns never do.
      const producedReview =
        state.producedReview ||
        ["synthesis_result", "html_report_content", "review_metrics"].some(
          (k) => k in stateDelta
        );

      return {
        ...state,
        phases,
        activeAgent,
        log,
        liveEntry: null,
        sessionState,
        producedReview,
      };
    }

    case "TICK":
      return { ...state, elapsedMs: action.elapsedMs };

    case "COMPLETE":
      // Authoritative end-of-run: the SSE stream closed (whole invocation done).
      // Finalize any phases/agents left mid-flight.
      return {
        ...state,
        isRunning: false,
        isComplete: true,
        liveEntry: null,
        phases: finalizePhases(state.phases),
      };

    case "ERROR":
      return { ...state, isRunning: false, error: action.message, liveEntry: null };

    default:
      return state;
  }
}

const initialState: ReviewHookState = {
  phases: buildInitialPhases(),
  activeAgent: null,
  log: [],
  liveEntry: null,
  sessionState: {},
  isComplete: false,
  isRunning: false,
  error: null,
  elapsedMs: 0,
  producedReview: false,
};

export function useAgentReview() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Accumulates partial text per (author, invocationId) — lives outside reducer
  // to avoid a React state update on every streaming token.
  const partialAccumRef = useRef<Map<string, string>>(new Map());

  const start = useCallback(
    async (
      payload: {
        userId: string;
        sessionId: string;
        messageText: string;
        appName?: string;
        customBaseUrl?: string;
        inlineFiles?: Array<{ displayName: string; data: string; mimeType: string }>;
        /** Friendly text to show in chat instead of messageText (e.g. for command sentinels). */
        displayText?: string;
      },
      seed?: ReviewSeed
    ) => {
      abortRef.current?.abort();
      if (timerRef.current) clearInterval(timerRef.current);
      partialAccumRef.current.clear();

      const controller = new AbortController();
      abortRef.current = controller;

      dispatch({ type: "START", seed });
      dispatch({ type: "USER_MESSAGE", text: payload.displayText ?? payload.messageText });
      startTimeRef.current = Date.now();

      timerRef.current = setInterval(() => {
        dispatch({ type: "TICK", elapsedMs: Date.now() - startTimeRef.current });
      }, 1000);

      try {
        // Guarantee session exists on the ADK backend before connecting to the SSE stream
        await getOrCreateSession(payload.userId, payload.sessionId, undefined, payload.appName, payload.customBaseUrl).catch((e) => {
          console.warn("[useAgentReview] Session pre-creation check warning:", e);
        });

        const stream = runSse(payload, controller.signal);
        const reader = stream.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw || raw === "[DONE]") continue;

            let event: AdkEvent;
            try {
              event = JSON.parse(raw);
            } catch {
              continue;
            }

            const key = `${event.author ?? "?"}_${event.invocationId ?? "?"}`;
            const textPart = event.content?.parts?.find((p) => p.text)?.text ?? "";

            if (event.partial && textPart) {
              // Accumulate streaming tokens — update live preview, don't add to log
              const soFar = (partialAccumRef.current.get(key) ?? "") + textPart;
              partialAccumRef.current.set(key, soFar);

              dispatch({
                type: "LIVE",
                entry: {
                  id: key,
                  author: event.author ?? "?",
                  text: soFar,
                  isPartial: true,
                  timestamp: toMillis(event.timestamp),
                  type: "text",
                },
              });
            } else {
              // Non-partial (final) event.
              // ADK already sends the COMPLETE text in the closing event, so we
              // must NOT concatenate the accumulated partial buffer onto it —
              // that would duplicate every message.
              // Only fall back to the buffer when the final event carries no text.
              const accumulated = partialAccumRef.current.get(key) ?? "";
              partialAccumRef.current.delete(key);

              let finalEvent = event;
              if (!textPart && accumulated) {
                finalEvent = injectText(event, accumulated);
              }

              dispatch({ type: "EVENT", event: finalEvent });
            }
          }
        }

        dispatch({ type: "COMPLETE" });
      } catch (err) {
        // If a newer run has started, this controller is stale — drop its result
        // so we don't terminate the fresh run.
        if (abortRef.current !== controller) return;
        // An aborted stream (stop() / unmount) is a normal cancellation, not an error.
        if (err instanceof DOMException && err.name === "AbortError") {
          dispatch({ type: "COMPLETE" });
        } else {
          dispatch({
            type: "ERROR",
            message: err instanceof Error ? err.message : "Unknown error",
          });
        }
      } finally {
        if (timerRef.current) clearInterval(timerRef.current);
      }
    },
    []
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    if (timerRef.current) clearInterval(timerRef.current);
    dispatch({ type: "COMPLETE" });
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    if (timerRef.current) clearInterval(timerRef.current);
    partialAccumRef.current.clear();
    dispatch({ type: "RESET" });
  }, []);

  return { ...state, start, stop, reset };
}

/** Returns a shallow clone of the event with the text part replaced. */
function injectText(event: AdkEvent, text: string): AdkEvent {
  return {
    ...event,
    partial: false,
    content: {
      ...(event.content ?? { parts: [] }),
      parts: [
        { text },
        ...(event.content?.parts?.filter((p) => !p.text) ?? []),
      ],
    },
  };
}
