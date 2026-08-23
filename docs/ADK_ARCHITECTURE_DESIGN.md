# Agent Guardian — ADK Architectural & Universal Frontend Design Specification

## 1. System Overview & Executive Summary

* **What is Agent Guardian:** An enterprise, production-grade multi-agent audit and remediation platform powered by **Google Agent Development Kit (ADK 2.0+)** and **Vertex AI Gemini** models.
* **Core Functionality:** Inspects codebases, executes pre-pass static analysis (`pyflakes`, `bandit`), dynamically crawls organizational governance from Confluence, applies an Evaluator-Critic quality gate loop, compiles standalone executive HTML reports, opens automated remediation PRs on GitHub and Bitbucket, and powers an interactive follow-up assistant.
* **Universal Frontend Layer:** A modern, responsive **Agent Guardian** web workspace built in Next.js 16 + React 19 that communicates universally with **any Google ADK agent application** through standard ADK SSE streaming and REST endpoints.

---

## 2. Core Architectural Components

### 2.1 Backend Pipeline Topology (`agent_guardian/agent.py`)

```
┌────────────────────────────────────────────────────────────────┐
│                     root_agent  (Supervisor)                   │
│  Accepts audit requests; delegates to review_pipeline          │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                  review_pipeline  (Sequential)                 │
│                                                                │
│  1. INGESTION & GOVERNANCE (ParallelAgent)                     │
│     ├── ingestion_agent        — clone repo / extract ZIP      │
│     └── confluence_rules_agent — fetch live governance rules   │
│                                                                │
│  2. PLANNING                                                   │
│     └── planning_agent — assigns files/modules to experts      │
│                                                                │
│  3. QUALITY GATE LOOP (LoopAgent)                              │
│     ├── parallel_review_experts  (ParallelAgent)               │
│     │   ├── adk_expert                                         │
│     │   ├── security_expert                                    │
│     │   ├── quality_expert                                     │
│     │   ├── governance_expert                                  │
│     │   └── code_validator_agent                               │
│     ├── evaluation_expert — scores 0-10; exits if ≥ threshold  │
│     └── revision_agent   — rewrites failing findings           │
│                                                                │
│  4. REPORTING & ARTIFACTS                                      │
│     ├── synthesis_agent — unified Markdown narrative           │
│     ├── metrics_agent   — health scores + Chart.js data        │
│     └── html_agent      — styled HTML dashboard artifact       │
│                                                                │
│  5. REMEDIATION & FOLLOW-UP                                    │
│     ├── remediation_agent — opens GitHub / Bitbucket PRs       │
│     └── followup_agent   — answers post-audit questions        │
└───────────────────────────┴────────────────────────────────────┘
```

### 2.2 ADK App Configuration & Resilience
Wraps `root_agent` with production runtime capabilities:
* **Context Caching (`ContextCacheConfig`)**: `min_tokens=15000`, `ttl_seconds=3600` for Vertex AI prompt caching, reducing token usage up to 90% during iterative audits.
* **Events Compaction (`EventsCompactionConfig`)**: `compaction_interval=1`, `overlap_size=1` to prevent context saturation across multiple `LoopAgent` cycles.
* **Session Resumability (`ResumabilityConfig`)**: `is_resumable=True` for persisting session state across reboots.
* **Node Hardening & Resilience**: Coordination agents wrapped with `harden_node()` (exponential backoff); expert agents wrapped with `resilient()` fallback to ensure partial reports complete gracefully.

---

## 3. Universal Google ADK Integration Protocol

### 3.1 Dynamic Backend App Discovery
The API gateway exposes dynamic discovery endpoints allowing the frontend to detect all registered ADK apps:
* `GET /list-apps` (and fallback `GET /apps`) returns `string[]` (e.g. `["agent_guardian", "installation_scripts", "code_auditor"]`).
* The frontend header displays a dynamic selector allowing instant app switching.

### 3.2 Dynamic Upstream Proxy Routing (`/api/adk/[...path]`)
* Supports custom upstream targeting via the `x-adk-base-url` header.
* Transparently forwards:
  * `POST /apps/{appName}/users/{userId}/sessions/{sessionId}` (Session creation)
  * `GET /apps/{appName}/users/{userId}/sessions/{sessionId}` (Session state retrieval)
  * `DELETE /apps/{appName}/users/{userId}/sessions/{sessionId}` (Session deletion)
  * `POST /run_sse` (Real-time SSE streaming)
  * `GET /apps/{appName}/users/{userId}/sessions/{sessionId}/artifacts` (Artifact downloads)

### 3.3 Gemini & ADK Part Parsing Taxonomy (`event-parser.ts`)

| ADK Part Shape | Semantic Purpose | Frontend Visual Representation |
|---|---|---|
| `text` | Streaming natural language response | Streaming markdown row in chat |
| `thought` / `reasoning` | Internal chain-of-thought | Collapsible violet `ThoughtView` card |
| `functionCall` / `function_call` | Tool invocation with JSON arguments | Interactive blue `ToolCallView` card with JSON inspection |
| `functionResponse` / `function_response` | Tool execution return value | Collapsible emerald `ToolResultView` card |
| `inlineData` / `inline_data` | Base64 encoded media/images | Media attachment view |
| `state_delta` | Granular `ctx.session.state` updates | Live state pills and Mission Control State Viewer |

---

## 4. Mission Control & Observability

### 4.1 Console Drawer Architecture
An expandable slide-out panel accessible from any page:
* **Raw Events Tab**: Live JSON stream of every incoming SSE chunk with search, filtering, and payload copy.
* **Audit State Tab**: Real-time tree view of all `ctx.session.state` keys (`codebase_map`, `review_plan`, `synthesis_report`, `metrics_json`).
* **Telemetry Tab**: Visual counters for input/output token counts, pipeline elapsed time, and per-agent latency.
* **Artifacts Tab**: Direct viewer and one-click download for `report.html` and remediation patches.

### 4.2 Distributed Tracing & Logging
* **OpenTelemetry**: Emits spans for each subagent, tool call, and LLM turn to Google Cloud Trace.
* **Datadog LLM Observability**: In-process auto-instrumentation for Gemini and ADK spans with unified service attribution (`DD_SERVICE=agent-guardian`, `DD_ENV=production`).

---

## 5. UI/UX Design System (Agent Guardian Workspace)

* **Design Foundation**: Built on clean responsive workspace patterns with modern typography (`Inter`, `Segoe UI`, `Fira Code`).
* **Brand Token Palette**:
  * **Primary Cobalt**: `#2525A3`
  * **Accent Ice Blue**: `#A6C3EE` / `#3B3BE8`
  * **Midnight Navy**: `#0E1F3D`
  * **Dark Surface**: `#212121` / `#171717`
* **Responsive Breakpoints**:
  * Desktop (≥1024px): Persistent sidebar, multi-column metrics, split diff viewer.
  * Tablet/Mobile (<1024px): Collapsible slide-over drawer, stacked cards, full-width touch prompt bar.

