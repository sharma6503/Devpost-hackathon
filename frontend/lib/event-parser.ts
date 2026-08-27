import type {
  AdkEvent,
  AgentName,
  AgentState,
  AgentStatus,
  LogEntry,
  PhaseId,
  PipelinePhase,
  PhaseStatus,
} from "@/types/adk";

const AGENT_PHASE_MAP: Record<string, PhaseId> = {
  ingestion_agent: "ingestion",
  confluence_rules_agent: "ingestion",
  planning_agent: "planning",
  code_quality_expert: "analysis",
  security_expert: "analysis",
  architecture_and_framework_expert: "analysis",
  governance_expert: "analysis",
  code_validator_agent: "analysis",
  evaluation_expert: "analysis",
  revision_agent: "analysis",
  loop_exit_agent: "analysis",
  synthesis_agent: "reporting",
  metrics_agent: "reporting",
  html_agent: "reporting",
  remediation_planner: "remediation",
  remediation_executor: "remediation",
};

const AGENT_LABELS: Record<string, string> = {
  ingestion_agent: "Ingestion",
  confluence_rules_agent: "Confluence Rules",
  planning_agent: "Planning",
  code_quality_expert: "Quality Expert",
  security_expert: "Security Expert",
  architecture_and_framework_expert: "ADK Expert",
  governance_expert: "Governance Expert",
  code_validator_agent: "Code Validator",
  evaluation_expert: "Evaluator",
  revision_agent: "Revision",
  synthesis_agent: "Synthesis",
  metrics_agent: "Metrics",
  html_agent: "HTML Report",
  remediation_planner: "Remediation Planner",
  remediation_executor: "Remediation Executor",
};

export function buildInitialPhases(): PipelinePhase[] {
  return [
    {
      id: "ingestion",
      label: "Ingestion",
      icon: "download",
      status: "pending",
      agents: [
        makeAgent("ingestion_agent"),
        makeAgent("confluence_rules_agent"),
      ],
    },
    {
      id: "planning",
      label: "Planning",
      icon: "map",
      status: "pending",
      agents: [makeAgent("planning_agent")],
    },
    {
      id: "analysis",
      label: "Analysis",
      icon: "search",
      status: "pending",
      agents: [
        makeAgent("code_quality_expert"),
        makeAgent("security_expert"),
        makeAgent("architecture_and_framework_expert"),
        makeAgent("governance_expert"),
        makeAgent("code_validator_agent"),
        makeAgent("evaluation_expert"),
        makeAgent("revision_agent"),
      ],
    },
    {
      id: "reporting",
      label: "Reporting",
      icon: "file-text",
      status: "pending",
      agents: [
        makeAgent("synthesis_agent"),
        makeAgent("metrics_agent"),
        makeAgent("html_agent"),
      ],
    },
    {
      id: "remediation",
      label: "Remediation",
      icon: "wrench",
      status: "pending",
      agents: [makeAgent("remediation_planner"), makeAgent("remediation_executor")],
    },
  ];
}

function makeAgent(name: string): AgentState {
  return {
    name: name as AgentName,
    label: AGENT_LABELS[name] ?? name,
    status: "pending",
  };
}

export interface ParsedUpdate {
  phases: PipelinePhase[];
  activeAgent: string | null;
  newLogEntry: LogEntry | null;
  stateDelta: Record<string, unknown>;
  isComplete: boolean;
}

/**
 * Monotonic suffix for synthetic log-entry ids. `Date.now()` alone collides when
 * two events are processed in the same millisecond (e.g. two back-to-back
 * `transfer_to_agent` calls), which produces duplicate React keys in the trace
 * list. Appending an ever-increasing counter guarantees per-entry uniqueness
 * regardless of timestamp or a missing/duplicated `event.id`.
 */
let __logEntrySeq = 0;
function fallbackLogId(prefix = "evt"): string {
  __logEntrySeq += 1;
  return `${prefix}_${Date.now()}_${__logEntrySeq}`;
}

/**
 * ADK event timestamps are SECONDS since epoch (adk-web renders
 * `new Date(t * 1000)`); the UI works in milliseconds. Feeding seconds into
 * `new Date()` lands at Jan 1 1970 — which displays as a constant "08:00:00"
 * in a UTC+8 timezone. Values already in ms (> 1e12 ≈ Sep 2001) pass through.
 */
export function toMillis(ts?: number): number {
  if (!ts) return Date.now();
  return ts < 1e12 ? Math.round(ts * 1000) : ts;
}

/**
 * Consecutive-duplicate guard for the chat log. ADK can surface the same logical
 * message more than once (a streamed final plus an aggregated copy, or a re-delivered
 * event), which otherwise shows up twice in the chat. Treat an entry as a duplicate of
 * the previous one when the event id matches, or when it's the same text from the same
 * author back-to-back.
 */
export function isDuplicateLog(prev: LogEntry | undefined, next: LogEntry): boolean {
  if (!prev) return false;
  if (prev.id === next.id) return true;
  return (
    prev.type === "text" &&
    next.type === "text" &&
    prev.author === next.author &&
    prev.text === next.text
  );
}

export function applyEvent(
  current: PipelinePhase[],
  event: AdkEvent,
  activeAgent: string | null
): ParsedUpdate {
  // Live reducer path: clone first so the array held in React state is never mutated
  // in place and the reducer receives a fresh `phases` reference to render.
  return applyEventInto(deepClonePhases(current), event, activeAgent);
}

/**
 * Mutating variant of {@link applyEvent}. Applies the event directly to the supplied
 * `phases` array WITHOUT cloning, and returns that same array. Use this for batch
 * reconstruction of a full session (potentially thousands of events): a fresh deep
 * clone per event there is pure allocation churn that blocks the main thread. The
 * live reducer must keep using {@link applyEvent}, which clones for immutability.
 */
export function formatAgentAuthor(raw?: string): string {
  if (!raw) return "Agent";
  if (raw === "user" || raw === "USER" || raw === "Operator") return "You";
  if (AGENT_LABELS[raw]) return AGENT_LABELS[raw];
  return raw
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function applyEventInto(
  phases: PipelinePhase[],
  event: AdkEvent,
  activeAgent: string | null
): ParsedUpdate {
  let newActiveAgent = activeAgent;
  let newLogEntry: LogEntry | null = null;
  const stateDelta: Record<string, unknown> = {};
  const isComplete = false;

  const rawAuthor = event.author || "agent";
  const author = rawAuthor.toLowerCase();
  const phaseId = AGENT_PHASE_MAP[author];

  // Activate the agent + phase
  if (author && author !== "user") {
    newActiveAgent = rawAuthor;
    if (phaseId) {
      for (const phase of phases) {
        if (phase.id === phaseId) {
          if (phase.status === "pending") phase.status = "active";
          for (const agent of phase.agents) {
            if (agent.name.toLowerCase() === author) {
              if (agent.status === "pending") agent.status = "running";
              const textPart = event.content?.parts?.find((p) => p.text);
              if (textPart?.text) {
                agent.lastMessage = textPart.text.slice(0, 120);
              }
            }
          }
        }
      }
    } else {
      // Dynamic agent not mapped to predefined phases
      let customPhase = phases.find((p) => p.id === "execution" || p.id === "analysis");
      if (!customPhase && phases.length > 0) {
        customPhase = phases[0];
      }
      if (customPhase) {
        if (customPhase.status === "pending") customPhase.status = "active";
        let agent = customPhase.agents.find((a) => a.name.toLowerCase() === author);
        if (!agent) {
          agent = {
            name: rawAuthor as AgentName,
            label: formatAgentAuthor(rawAuthor),
            status: "running",
          };
          customPhase.agents.push(agent);
        } else {
          agent.status = "running";
        }
      }
    }
  }

  // Mark agent as done if turn is complete
  if (event.turnComplete) {
    for (const phase of phases) {
      for (const agent of phase.agents) {
        if (agent.name.toLowerCase() === author && agent.status === "running") {
          agent.status = "done";
        }
      }
      const allDone = phase.agents.every(
        (a) => a.status === "done" || a.status === "pending"
      );
      const anyDone = phase.agents.some((a) => a.status === "done");
      if (allDone && anyDone) phase.status = "done";
    }
    newActiveAgent = null;
  }

  // Build log entry for all ADK part types (text, functionCall, functionResponse, thought, etc.)
  const parts = event.content?.parts ?? [];
  const textPart = parts.find((p) => p.text);
  const thoughtPart = parts.find((p) => p.thought);
  const callPart = parts.find((p) => p.functionCall || p.function_call);
  const responsePart = parts.find((p) => p.functionResponse || p.function_response);
  const transferTo = event.actions?.transferToAgent;

  if (textPart?.text && !event.partial) {
    newLogEntry = {
      id: event.id ?? fallbackLogId(),
      author: event.author,
      text: textPart.text,
      isPartial: false,
      timestamp: toMillis(event.timestamp),
      type: "text",
    };
  } else if (callPart && !event.partial) {
    const callData = callPart.functionCall || callPart.function_call || (callPart as any);
    newLogEntry = {
      id: event.id ?? fallbackLogId("tool_call"),
      author: event.author,
      text: `Invoked tool: ${callData.name}`,
      isPartial: false,
      timestamp: toMillis(event.timestamp),
      type: "tool_call",
      toolData: {
        name: callData.name,
        args: callData.args ?? {},
      },
    };
  } else if (responsePart && !event.partial) {
    const respData = responsePart.functionResponse || responsePart.function_response || (responsePart as any);
    newLogEntry = {
      id: event.id ?? fallbackLogId("tool_result"),
      author: event.author,
      text: `Result from ${respData.name}`,
      isPartial: false,
      timestamp: toMillis(event.timestamp),
      type: "tool_result",
      toolData: {
        name: respData.name,
        response: respData.response ?? {},
      },
    };
  } else if (transferTo && !event.partial) {
    newLogEntry = {
      id: event.id ?? fallbackLogId("transfer"),
      author: event.author,
      text: `Delegated execution to ${formatAgentAuthor(transferTo)}`,
      isPartial: false,
      timestamp: toMillis(event.timestamp),
      type: "transfer",
    };
  } else if (thoughtPart?.thought && !event.partial) {
    newLogEntry = {
      id: event.id ?? fallbackLogId("thought"),
      author: event.author,
      text: thoughtPart.thought,
      isPartial: false,
      timestamp: toMillis(event.timestamp),
      type: "thought",
    };
  }

  // State delta
  if (event.actions?.stateDelta) {
    Object.assign(stateDelta, event.actions.stateDelta);
  }

  // Attach rawEvent and stateDelta to the new log entry
  if (newLogEntry) {
    newLogEntry.rawEvent = slimEvent(event);
    if (event.actions?.stateDelta && Object.keys(event.actions.stateDelta).length > 0) {
      newLogEntry.stateDelta = event.actions.stateDelta;
    }
  }

  return {
    phases,
    activeAgent: newActiveAgent,
    newLogEntry,
    stateDelta,
    isComplete,
  };
}

/**
 * Recursively merges partial source objects into target without mutating target.
 * Retains sibling fields on nested structures (review_metrics, module_map, review_plan).
 */
export function deepMergeState<T extends Record<string, any>>(target: T, source: Partial<T>): T {
  if (!source || typeof source !== "object") return target;
  const result: any = { ...target };
  for (const [key, value] of Object.entries(source)) {
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      typeof result[key] === "object" &&
      result[key] !== null &&
      !Array.isArray(result[key])
    ) {
      result[key] = deepMergeState(result[key], value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function deepClonePhases(phases: PipelinePhase[]): PipelinePhase[] {
  return phases.map((p) => ({
    ...p,
    agents: p.agents.map((a) => ({ ...a })),
  }));
}

/**
 * Returns a copy of the event with bulky inline payloads elided (e.g. base64 ZIP
 * uploads). Keeps the per-row `rawEvent` small enough to retain in React state for the
 * inspector without holding multi-MB blobs across every log entry — echoing adk-web's
 * choice not to keep heavy event detail in the rendered list. Cheap (no JSON
 * stringify): only the inline `data` string length is inspected.
 */
function slimEvent(event: AdkEvent): AdkEvent {
  const parts = event.content?.parts;
  if (!parts?.length) return event;

  let changed = false;
  const slimmed = parts.map((p) => {
    if (p.inlineData?.data && p.inlineData.data.length > 256) {
      changed = true;
      return {
        ...p,
        inlineData: {
          ...p.inlineData,
          data: `[${p.inlineData.data.length} bytes elided]`,
        },
      };
    }
    return p;
  });

  if (!changed) return event;
  return { ...event, content: { ...event.content!, parts: slimmed } };
}

export function getPhaseStatus(phases: PipelinePhase[], id: PhaseId): PhaseStatus {
  return phases.find((p) => p.id === id)?.status ?? "pending";
}

/**
 * Finalize the pipeline view when the run truly ends (SSE stream closed):
 * any still-active phase → done, any still-running agent → done.
 * Pending agents/phases are left untouched (they never started, e.g. a skipped
 * conditional branch), so the UI honestly reflects what actually executed.
 */
export function finalizePhases(phases: PipelinePhase[]): PipelinePhase[] {
  const next = deepClonePhases(phases);
  for (const phase of next) {
    if (phase.status === "active") phase.status = "done";
    for (const agent of phase.agents) {
      if (agent.status === "running") agent.status = "done";
    }
  }
  return next;
}

/**
 * Safely extracts and validates a letter grade (A-F with optional +/-).
 * Rejects non-grade strings like "Not provided or skipped.", empty strings, etc.
 */
export function cleanGrade(raw?: any): string | undefined {
  if (!raw || typeof raw !== "string") return undefined;
  const trimmed = raw.trim();
  if (/^[A-F][+-]?$/i.test(trimmed)) {
    return trimmed.toUpperCase();
  }
  const match = trimmed.match(/^Grade\s*:?\s*([A-F][+-]?)/i);
  if (match) {
    return match[1].toUpperCase();
  }
  return undefined;
}
