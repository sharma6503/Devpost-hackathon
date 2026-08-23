export interface Part {
  text?: string;
  thought?: string;
  functionCall?: {
    id?: string;
    name: string;
    args: Record<string, unknown>;
  };
  function_call?: {
    id?: string;
    name: string;
    args: Record<string, unknown>;
  };
  functionResponse?: {
    id?: string;
    name: string;
    response: Record<string, unknown>;
  };
  function_response?: {
    id?: string;
    name: string;
    response: Record<string, unknown>;
  };
  inlineData?: {
    displayName?: string;
    display_name?: string;
    data: string;
    mimeType?: string;
    mime_type?: string;
  };
  inline_data?: {
    displayName?: string;
    display_name?: string;
    data: string;
    mimeType?: string;
    mime_type?: string;
  };
}

export interface Content {
  parts: Part[];
  role?: "user" | "model" | "system" | string;
}

export interface EventActions {
  stateDelta?: Record<string, unknown>;
  artifactDelta?: Record<string, unknown>;
  transferToAgent?: string;
  escalate?: boolean;
  skipSummarization?: boolean;
  requestedAuthConfigs?: Record<string, unknown>;
}

export interface AdkEvent {
  id: string;
  invocationId: string;
  author: string;
  content?: Content;
  actions?: EventActions;
  partial?: boolean;
  turnComplete?: boolean;
  timestamp: number;
  longRunningToolIds?: string[];
  errorCode?: string;
  errorMessage?: string;
}

export interface Session {
  id: string;
  appName: string;
  userId: string;
  state: Partial<ReviewState>;
  events: AdkEvent[];
  lastUpdateTime: number;
}

export interface ReviewState {
  user_request: string;
  /** Login-captured caller identity, seeded into session state at creation.
   * Session-constant (preserved across per-review resets) and surfaced in
   * telemetry; user-claimed, not an auth assertion. */
  user_department?: string;
  user_country?: string;
  raw_codebase: string;
  code_logic: string;
  code_config: string;
  code_docs: string;
  module_map: Record<string, string[]>;
  is_large_codebase: boolean;
  logic_file_count: number;
  total_file_count: number;
  confluence_rules: string;
  review_plan: string;
  governance_review_result: string;
  adk_review_result: string;
  quality_review_result: string;
  security_review_result: string;
  validation_result: string;
  evaluation_result: string;
  evaluation_grade: string;
  evaluation_feedback: string;
  weakest_agent: string;
  synthesis_result: string;
  review_metrics: ReviewMetrics;
  metrics_chart_b64: string;
  html_report_content: string;
  scorecard_html: string;
  metrics_chart_html: string;
  repo_metadata_html: string;
  expert_reviews_html: string;
  remediation_plan: string;
  /** http(s) PR URL ONLY (empty unless a PR was actually created). */
  remediation_pr_url: string;
  remediation_skipped: boolean;
  /** Lifecycle status, kept separate from the URL. */
  remediation_status?: "" | "pending_approval" | "created" | "skipped" | "dry_run" | "no_target" | "failed";
  remediation_pending_approval?: boolean;
  /** Markdown summary of the proposed PR, shown while pending approval. */
  remediation_plan_summary?: string;
}

/** Actual shape written by metrics_agent.py */
export interface ReviewMetrics {
  /** Nested scores object (primary) */
  scores?: {
    security?: number;
    quality?: number;
    architecture?: number;
    governance?: number;
    validation?: number;
    overall?: number;
  };
  /** Nested severity counts (primary) */
  severity?: {
    critical?: number;
    high?: number;
    medium?: number;
    low?: number;
  };
  /** Issue counts by agent category */
  category?: Record<string, number>;
  total?: number;
  [key: string]: unknown;
}

export type AgentName =
  | "ingestion_agent"
  | "confluence_rules_agent"
  | "planning_agent"
  | "code_quality_expert"
  | "security_expert"
  | "architecture_and_framework_expert"
  | "governance_expert"
  | "code_validator_agent"
  | "evaluation_expert"
  | "revision_agent"
  | "synthesis_agent"
  | "metrics_agent"
  | "html_agent"
  | "remediation_planner"
  | "remediation_executor"
  | "root_agent"
  | (string & {});

export type PhaseId =
  | "ingestion"
  | "planning"
  | "analysis"
  | "reporting"
  | "remediation"
  | (string & {});

export type AgentStatus = "pending" | "running" | "done" | "failed";
export type PhaseStatus = "pending" | "active" | "done";

export interface AgentState {
  name: AgentName;
  label: string;
  status: AgentStatus;
  lastMessage?: string;
}

export interface PipelinePhase {
  id: PhaseId;
  label: string;
  icon: string;
  status: PhaseStatus;
  agents: AgentState[];
}

export interface LogEntry {
  id: string;
  author: string;
  text: string;
  isPartial: boolean;
  timestamp: number;
  type: "text" | "tool_call" | "tool_result" | "transfer" | "thought" | "media";
  stateDelta?: Record<string, unknown>;
  rawEvent?: AdkEvent;
  toolData?: Record<string, unknown>;
}
