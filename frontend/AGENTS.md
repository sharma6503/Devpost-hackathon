# Agent Guardian — Frontend & Universal ADK Architecture Guide

This document defines the architectural patterns, runtime contracts, and conventions for engineers and AI agents extending the Agent Guardian web workspace.

---

## 1. Core Architecture Principles

1. **Universal ADK Compatibility**: The frontend must never assume hardcoded agent names or rigid schemas. Any standard Google ADK backend app running locally or remotely can be targeted dynamically.
2. **Streaming-First Architecture**: Live interactions flow through Server-Sent Events (`POST /run_sse` or `/api/adk/run_sse`). All agent outputs, tools, reasoning thoughts, and phase transitions must render progressively.
3. **Agent Guardian Design Standard**: UI layout, typography, and controls adhere strictly to clean design specifications (collapsible sidebar, sticky headers, auto-growing multi-line input, responsive drawer transitions, and spotlight search).
4. **Brand Design Identity**: Follow the established Cobalt (`#2525A3`), Ice Blue (`#A6C3EE`), and Dark Charcoal (`#212121`) design token hierarchy. Avoid hardcoded green/emerald or legacy purple hues for brand-level components.

---

## 2. Google ADK Integration Protocol

### 2.1 Upstream ADK Proxy (`frontend/app/api/adk/[...path]/route.ts`)
The proxy route handles client-to-backend communication:
- **Base URL Resolution**: Defaults to `NEXT_PUBLIC_API_URL` (or `http://127.0.0.1:8000`), but dynamically overrides if `x-adk-base-url` header is supplied.
- **Supported Endpoints**:
  - `GET /api/adk/list-apps` (or fallback `/api/adk/apps`) — Discovers registered ADK apps.
  - `POST /api/adk/apps/{appName}/users/{userId}/sessions/{sessionId}` — Creates a new ADK session.
  - `GET /api/adk/apps/{appName}/users/{userId}/sessions/{sessionId}` — Fetches persistent session state.
  - `DELETE /api/adk/apps/{appName}/users/{userId}/sessions/{sessionId}` — Deletes session.
  - `POST /api/adk/run_sse` — Runs streaming workflow.

### 2.2 Client SDK (`frontend/lib/adk-client.ts`)
- `listApps(customBaseUrl?: string)`: Queries upstream apps.
- `createSession(...)`: Initializes user session under `appName`.
- `runSse(...)`: Consumes the chunked SSE stream and dispatches parsed JSON events to listeners.
- `listArtifacts(...)` / `getArtifact(...)`: Interacts with ADK Artifact Services (`FileArtifactService` in development, `GcsArtifactService` in production).

### 2.3 Event Parser & State Accumulator (`frontend/lib/event-parser.ts`)
ADK events are processed into structured review state via `applyEventInto(state, event)`:
- **Gemini / ADK Parts**:
  - `text`: Appends text chunks to active agent log.
  - `thought` / `reasoning`: Maps to `type: "thought"` log entry with collapsible UI.
  - `functionCall` / `function_call`: Generates `type: "tool_call"` with parsed JSON arguments.
  - `functionResponse` / `function_response`: Maps to `type: "tool_result"` with response payload.
- **Dynamic Phase Registration**: When an event arrives with an unfamiliar author (e.g. `sql_optimizer`), `formatAgentAuthor(author)` converts it to Title Case and registers a new pipeline phase dynamically.
- **State Deltas**: State updates (`codebase_map`, `review_plan`, `synthesis_report`, `metrics_json`, `remediation_plan`) are stored into `state.sessionState`.

---

## 3. UI Component Structure

```
frontend/components/
├── adk/
│   └── ADKAgentChat.tsx       # Standalone plug-and-play ADK chat component
├── brand/
│   ├── AgentGuardianLogo.tsx  # Vector SVG Shield/Radar logo
│   └── ThemeProvider.tsx      # Dark / Light mode provider
├── guardian/
│   ├── GuardianHeader.tsx     # App selector dropdown, repo indicator, search & export trigger
│   ├── GuardianSidebar.tsx    # Chronological audit history, user manager, new audit CTA
│   └── ExportShareModal.tsx   # Share direct link, download markdown dossier or JSON telemetry
├── console/
│   └── UserConsoleDrawer.tsx  # Mission Control: Raw events, state JSON, telemetry, artifacts
├── review/
│   ├── ChatLogRow.tsx         # Message row, ToolCallView, ToolResultView, ThoughtView
│   ├── UserTraceBar.tsx       # Mini progress tracker
│   ├── AuditSearchModal.tsx   # Spotlight search (⌘K / Ctrl+K)
│   ├── EventInspectorModal.tsx# Deep event detail inspection modal
│   ├── ActivityFeed.tsx       # Live status feed
│   └── StateDeltaCard.tsx     # Live state update notifications
└── results/
    ├── ReportViewer.tsx       # Executive HTML report renderer
    ├── MetricsOverview.tsx    # Health score gauges & charts
    └── RemediationModal.tsx   # Git diff review & one-click PR modal
```

---

## 4. Key React Hooks

- **`useAgentReview` (`frontend/hooks/useAgentReview.ts`)**:
  - Manages session lifecycle (`start`, `resume`, `stop`).
  - Maintains `liveLogs`, `sessionState`, `phases`, and `activeAgent`.
  - Connects to SSE stream and handles errors/reconnections gracefully.
- **`useTheme` (`frontend/components/brand/ThemeProvider.tsx`)**:
  - Provides `theme` (`dark` | `light`), `toggleTheme`, and system preference syncing.

---

## 5. Development & Contribution Rules

1. **Zero Type Errors**: Always verify changes using `npx tsc --noEmit` before committing.
2. **Production Build Cleanliness**: Ensure `npm run build` succeeds without build or SSR warnings.
3. **No Hardcoded App Routes**: All ADK requests must route through `adk-client.ts` with dynamic `appName`.
4. **Sanitize Monospace & Code**: Code blocks and JSON trees must use `Fira Code` with proper contrast against light/dark canvases.

