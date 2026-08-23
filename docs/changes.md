# Changes — Observability Fix + Targeted Decoupling

Date: 2026-07-30

Two goals, both scoped tight: fix Datadog observability, and apply high-value decoupling.

---

## ROOT CAUSE of "no traces" (found by live experiment + Datadog MCP)

`DD_APM_TRACING_ENABLED` was left **on** (its default). In agentless LLM Observability mode, when APM
tracing is enabled ddtrace ships the spans to the **APM trace intake** and the LLM Obs writer never
posts to the **LLM Obs intake** — so nothing appears in LLM Observability. Proven by a controlled
run: with APM on, `DD_TRACE_DEBUG` showed the `LLMObsSpanWriter` start/stop with **no send**; setting
`DD_APM_TRACING_ENABLED=false` produced `sent N LLMObs span events to llmobs-intake.us5` and the
`root_agent`/`google_adk`/`google_genai` spans then appeared in Datadog (clean root, no cycle). This
matches the ADK Datadog doc (`DD_APM_TRACING_ENABLED=false # only if not using Datadog APM`) and is
the setting the working sibling agent had that this one lacked.

**Fix:** `agent_guardian/agent.py` `_init_datadog_llmobs()` now does
`os.environ.setdefault("DD_APM_TRACING_ENABLED", "false")` before importing ddtrace — so LLM Obs
ships regardless of how the app is launched (adk web, api_server, uvicorn, Cloud Run). An operator
who also wants APM can still override it. Dockerfile ENV, `.env.example`, and both launch scripts
also default it to false.

(Ruled out along the way, with evidence: not the ddtrace version, not the org/key — intake returns
202 and spans land in the team-visible org — and not the long-lived MCP `ClientSession` span; the
sibling agent is ADK+MCP on the same 4.13.0rc1 and works.)

## Background: earlier framing

The reported symptom was "traces never reach Datadog." Verifying against the Datadog MCP
disproved it — the `agent-guardian` ML app was already receiving current-commit spans on **us5**,
with both integrations working: `google_adk` (agent/tool/workflow) and `google_genai` (LLM spans
with real token counts and cost). The actual problems in the data were:

- Every trace deep-linked through `switch_to_user/53a530d3-…` → spans landed in a **personal /
  sandbox Datadog account**, not the team org. That is why the team "couldn't see traces."
- `service` / `env` / `version` span tags were **empty** → unattributable, invisible in APM and in
  any service/env-filtered view.
- A **"CPQ Quote Optimization Agent"** was emitting under the same hardcoded
  `ml_app=agent-guardian` → namespace collision from a shared key + hardcoded name.
- Config existed **nowhere reproducible** — no `DD_*` in `.env.example`, none in the deploy
  forward-list → genuinely unset in local envs, so it "never worked" locally while flowing to
  someone's sandbox.

Fix aligns the app with ADK's documented Datadog integration (env-vars + `ddtrace-run`) **and**
fixes attribution / org / ml_app.

---

## Part A — Datadog observability

### `agent_guardian/agent.py`
- Removed the hardcoded `from ddtrace.llmobs import LLMObs` + `LLMObs.enable(...)` block that ran
  at module import, plus the now-orphaned duplicate `import os`.
- Added a Datadog bootstrap at the top of the module: `load_dotenv()` then `import ddtrace.auto`,
  which reads the `DD_*` env and auto-instruments `google_adk` + `google_genai`. This is the
  cross-platform equivalent of `ddtrace-run` — chosen because `ddtrace-run` mangles CLI args around
  the `adk.EXE` console-script wrapper on Windows (`adk web` fails with `No such command '-'`).
  Because `.env` is loaded before `ddtrace.auto`, putting `DD_*` in `.env` is enough — no wrapper,
  no manual `export`. Works for `adk web`, `adk api_server`, and uvicorn.

### `Dockerfile`
- CMD stays plain uvicorn (`uv run uvicorn api.main:app …`) — instrumentation is in-process via
  `ddtrace.auto`, so no `ddtrace-run` wrapper.
- Added non-secret `ENV` defaults: `DD_LLMOBS_ENABLED=true`, `DD_LLMOBS_ML_APP=agent-guardian`,
  `DD_LLMOBS_AGENTLESS_ENABLED=true`, `DD_APM_TRACING_ENABLED=false`, `DD_SITE=us5.datadoghq.com`,
  `DD_SERVICE=agent-guardian`, `DD_ENV=production`. `DD_SERVICE`/`DD_ENV`/`DD_VERSION` are the
  unified service tags that populate the previously-empty span tags.
- `DD_API_KEY` remains a deploy secret (never baked into the image). `DD_VERSION` set from the git
  SHA at deploy time.

### `.env.example`
- Added a documented `Datadog LLM Observability` block. Because `agent.py` loads `.env` before
  `ddtrace.auto`, setting `DD_*` in `.env` is sufficient for local dev — no `export`, no
  `ddtrace-run`. Includes the team-org-key warning.

### `scripts/run_adk_web.sh` + `scripts/run_adk_web.ps1` (new)
- Convenience launchers for local `adk web`: load `.env` into the environment, fill DD defaults,
  warn if `DD_API_KEY` is unset, then run `uv run adk web .` (bash + PowerShell twins).

### `scripts/deploy_to_agent_engine.py`
- Added `DD_API_KEY`, `DD_SITE`, `DD_LLMOBS_ENABLED`, `DD_LLMOBS_ML_APP`,
  `DD_LLMOBS_AGENTLESS_ENABLED`, `DD_APM_TRACING_ENABLED`, `DD_SERVICE`, `DD_ENV`, `DD_VERSION` to
  `ENV_VARS_TO_FORWARD` so the Agent Engine deploy path carries them.

---

## Part B — Targeted decoupling

### `agent_guardian/utils/mcp_factory.py`
GitHub MCP-toolset construction was triplicated with drifted timeouts / filters / scopes. Consolidated:
- Added `_build_github_toolset(tool_filter, github_toolsets, timeout)` — the single construction site.
- `get_github_mcp_toolset(tool_filter=GITHUB_READ_TOOLS)` — parameterized read builder, memoized per
  filter. Added `GITHUB_INGEST_TOOLS` constant for the wider ingestion filter.
- Added `get_github_write_mcp_toolset()` — read/write scope (`repo,files,pull_requests,git`), no
  filter, timeout 10, for remediation.

### `agent_guardian/sub_agents/ingestion_agent.py`
- Replaced the ~45-line inline MCP build with `get_github_mcp_toolset(GITHUB_INGEST_TOOLS)`.
- Dropped the now-unused `SafeMcpToolset` import (kept `get_binary_path`, still used below).

### `agent_guardian/sub_agents/remediation_agent.py`
- Replaced the ~55-line inline MCP build + fallback branch with `get_github_write_mcp_toolset()`,
  keeping the REST-fallback tools for when MCP is unavailable.
- Dropped the now-unused `get_binary_path` import (kept `SafeMcpToolset`, still used below).

### `agent_guardian/utils/callbacks.py`
- Split the god `constitution_callback` (~8 unrelated jobs) into single-purpose helpers:
  `_seed_default_state`, `_inject_prompt_metadata`, `_load_constitution`, `_capture_event_horizon`,
  `_extract_repo_authorization`, `_apply_hitl_remediation_commands`. `constitution_callback` is now
  a thin orchestrator; behavior and ADK wiring unchanged.
- Added `parse_repo_reference(text) -> dict` — the single source of truth for parsing github.com /
  bitbucket.org URLs into `{owner, repo, ref?}`.

---

## Verification

- Import smoke: `uv run python -c "import agent_guardian.agent"` → OK, `root_agent` builds.
- Ruff: clean on all fully-owned files (`agent.py`, `callbacks.py`, `mcp_factory.py`,
  `ingestion_agent.py`).
- Unit tests: `uv run pytest tests/unit -q` → **150 passed**.
  - One failure — `tests/unit/test_config.py::test_default_config_loading` — is **pre-existing and
    unrelated**: it asserts `root_model == "gemini-3.1-flash-lite"` but the config default is
    `gemini-3.7-flash`. No model config was touched by this work.
- `ddtrace-run` resolves as a valid console script from the `ddtrace` dep (Dockerfile CMD is valid).

---

## Full Codebase Analysis, Test Suite Hardening & Hygiene Updates

Date: 2026-08-23

### 1. Test Suite Integrity & Mock Isolation (160/160 Tests Passing)
- **Eliminated Global Test Pollution (`tests/e2e/conftest.py`):**
  - Removed top-level import-time `sys.modules.setdefault(...)` and un-scoped `patch.object(SafeMcpToolset, ...).start()`.
  - Scoped all MCP and TokenManager mock patches inside the `mock_mcp_and_token_manager` fixture with automatic cleanup.
  - Fixed `_clear_agent_clients` teardown to stop popping `_resolved_model` from `__pydantic_private__`, which previously broke Pydantic private attribute descriptors on `LlmAgent` and caused `TypeError: Expected agent to have tools and canonical_model attributes` in downstream test runs (`test_pipeline_flow.py`).
- **ResilientAgent Delegate Properties (`agent_guardian/utils/resilience.py`):**
  - Added property delegations (`tools`, `canonical_model`, `model`, `output_key`) to `ResilientAgent` so wrapper instances are fully compatible with ADK's internal LLM flow inspection (`_preprocess_async`).
- **Pickling & Serialization Test Hardening (`tests/unit/test_serialization.py`):**
  - Added recursive `_clean_mocks` helper in `test_root_agent_and_app_pickling` to purge transient test mock client references before pickling, ensuring robust pickle test validation across Vertex AI Agent Engine and session stores.
- **Test Result:** 100% test pass rate across the full suite (160 passed in 64s).

### 2. Repo Hygiene & Unwanted File Removal
- Removed unwanted scratch file: `frontend/CLAUDE.md`.
- Verified `.gitignore` and `.dockerignore` for complete exclusion of Python/Next.js/IDE build and cache artifacts.
- Fixed all whitespace and import lint issues with `ruff` across `scripts/`, `tests/`, and root files.

### 3. Documentation Modernization & Synchronization
- **`frontend/README.md`:** Modernized from default template into comprehensive documentation covering features, Next.js 16/React 19 tech stack, SSE streaming, API proxy architecture, and development workflow.
- **`docs/production_architecture.md`:** Corrected Mermaid code fence syntax and validated serverless GCP topology descriptions.
- **`docs/ADK_ARCHITECTURE_DESIGN.md`:** Re-verified pipeline stage definitions against ADK 2.0+ implementation.

---

## Brand Redesign, Responsive ChatGPT UI Kit, and Universal ADK Integration

Date: 2026-08-23

### 1. Vector Logo & Brand Palette Alignment
- **Custom SVG Shield/Radar Brand Asset (`AgentGuardianLogo.tsx`):**
  - Designed responsive vector logo with radial gradients and brand glows matching the official vector assets.
  - Replaced legacy purple/emerald palettes with the official Agent Guardian design system:
    - **Primary Brand Cobalt:** `#2525A3`
    - **Ice Blue Accents:** `#A6C3EE` / `#3B3BE8`
    - **Deep Midnight Navy:** `#0E1F3D`
    - **Dark Canvas / Sidebar:** `#212121` / `#171717`
- **Component Theming:**
  - Standardized badges, active pills, status indicators, and focus outlines across all components (`ChatLogRow`, `ConsoleDrawer`, `UserTraceBar`, `ChatGPTHeader`, `ChatGPTSidebar`, `MetricsOverview`).

### 2. Responsive ChatGPT UI Kit Layout & Typography
- **Typography:** Aligned all fonts and headings with the ChatGPT UI Kit specification using `Inter`, `Segoe UI`, and `Fira Code` (monospace code & JSON).
- **Responsive Layout:**
  - Collapsible sidebar with session history and mobile drawer overlay (`ChatGPTSidebar.tsx`).
  - Sticky header (`ChatGPTHeader.tsx`) with active repository pills, theme toggles, and search shortcuts.
  - Multi-line auto-growing prompt input with file drop support and keyboard submission.

### 3. Mission Control Console Drawer & Raw Event Inspection Fix
- **Fix for Raw Event Inspection:**
  - Resolved event accumulation logic in `useAgentReview.ts` and `ConsoleDrawer.tsx` to ensure every raw ADK SSE chunk is captured, indexed, and inspectable in the JSON viewer.
  - Added full search filtering and one-click copy for raw event payloads.
- **State Delta Tracking:** Real-time visual tracking of `ctx.session.state` updates (`codebase_map`, `review_plan`, `synthesis_report`, `metrics_json`).

### 4. Universal Google ADK Agent Compatibility
- **Dynamic ADK App Discovery (`GET /list-apps` & `GET /apps`):**
  - Frontend auto-discovers all registered apps on the backend and surfaces them in the header dropdown.
- **Universal Upstream Proxy (`/api/adk/[...path]`):**
  - Supports dynamic routing to arbitrary ADK servers via the `x-adk-base-url` header.
- **Complete ADK & Gemini Part Coverage (`event-parser.ts` & `ChatLogRow.tsx`):**
  - `thought` / `reasoning` → Collapsible `ThoughtView` cards.
  - `functionCall` / `function_call` → Interactive `ToolCallView` cards with JSON argument inspection.
  - `functionResponse` / `function_response` → Emerald `ToolResultView` cards.
  - Dynamic author resolution (`formatAgentAuthor`) to auto-format unknown agent names and create pipeline phases on the fly.
- **Embeddable Component (`<ADKAgentChat />`):** Standalone zero-friction component to embed any ADK agent into any page.


