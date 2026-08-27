# Agent Guardian 🛡️

**Agent Guardian** is an enterprise, production-grade multi-agent audit and remediation platform powered by the **Google Agent Development Kit (ADK 2.0+)** and **Vertex AI Gemini** models. It autonomously inspects codebases, enforces organizational and security standards, runs static analysis, generates executive dashboards, and opens automated pull requests — coupled with a modern, responsive **Agent Guardian web workspace** that connects universally to any Google ADK agent.

---

## 🌟 Key Capabilities

- **Universal Google ADK Agent Workspace:** Works seamlessly with `agent_guardian` and connects to **any** Google ADK agent application with dynamic discovery (`GET /list-apps`), upstream proxying, and live session management.
- **Multi-Agent Audit Fleet:** Specialized parallel expert agents for ADK best practices, OWASP security, code quality, enterprise governance, and logical correctness.
- **Interactive Tool & Thought Visualizations:** Native rendering of agent reasoning (`thought` / CoT chains), tool calls (`functionCall` with JSON parameter inspect), and tool outputs (`functionResponse`).
- **Pre-pass Static Analysis:** Automated `pyflakes` and `bandit` scans executed prior to LLM evaluation to pre-populate structured findings with exact file and line references.
- **Dynamic Policy & Governance Injection:** Live crawling of corporate standards from **Confluence** (URL, space, or markdown) to keep audits synchronized with organizational policies.
- **Evaluator-Critic Quality Gate:** Iterative evaluation loop (`LoopAgent`) ensuring findings meet strict evidence, specificity, and actionability thresholds before report generation.
- **Automated SCM Remediation:** One-click automated branch and Pull Request creation on **GitHub** and **Bitbucket** with human-in-the-loop (HITL) review.
- **Mission Control Console Drawer:** Real-time observability dashboard featuring raw ADK event inspection, metrics cards, token consumption telemetry, and live artifact browsers.
- **Executive Dashboard Reports:** Zero-dependency, standalone HTML/Chart.js audit reports with Ingram Micro brand styling.

---

## 🎨 Modern Brand & Responsive Workspace Experience

Agent Guardian features a redesigned visual identity inspired by modern enterprise design principles:
- **Brand Palette:** Deep Cobalt (`#2525A3`), Ice Blue accents (`#A6C3EE` / `#3B3BE8`), Midnight Navy (`#0E1F3D`), and Charcoal dark canvas (`#212121`).
- **Agent Guardian Workspace Canvas:** Collapsible sidebar with session history, sticky top navigation with live repository pills, interactive bottom prompt bar with multi-line auto-grow, and instant sample query cards.
- **Responsive Layout:** Optimized for desktop, tablet, and mobile with auto-collapsing sidebars and touch-friendly drawers.
- **Theme Support:** Seamless dark/light mode switching with smooth transitions.
- **Audit Search (`Cmd+K` / `Ctrl+K`):** Fast fuzzy search across historical sessions and audit results.

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                     root_agent  (Supervisor)                   │
│  Accepts user requests; delegates to review_pipeline           │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                  review_pipeline  (Sequential)                 │
│                                                                │
│  1. INGESTION & RULES  (ParallelAgent)                         │
│     ├── ingestion_agent        — clone repo / extract ZIP      │
│     └── confluence_rules_agent — fetch live governance rules   │
│                                                                │
│  2. PLANNING                                                   │
│     └── planning_agent — assigns files/modules to experts      │
│                                                                │
│  3. QUALITY GATE  (LoopAgent)                                  │
│     ├── parallel_review_experts  (ParallelAgent)               │
│     │   ├── adk_expert                                         │
│     │   ├── security_expert                                    │
│     │   ├── quality_expert                                     │
│     │   ├── governance_expert                                  │
│     │   └── code_validator_agent                               │
│     ├── evaluation_expert — scores 0-10; exits if ≥ threshold  │
│     └── revision_agent   — rewrites failing findings           │
│                                                                │
│  4. REPORTING & SYNTHESIS                                      │
│     ├── synthesis_agent — unified Markdown narrative           │
│     ├── metrics_agent   — health scores + Chart.js data        │
│     └── html_agent      — styled HTML dashboard artifact       │
│                                                                │
│  5. REMEDIATION  (Human-in-the-Loop)                           │
│     └── remediation_agent — opens GitHub / Bitbucket PRs       │
│                                                                │
│  6. INTERACTIVE FOLLOW-UP                                      │
│     └── followup_agent — answers post-audit questions          │
└────────────────────────────────────────────────────────────────┘
```

### Shared State Protocol (`ctx.session.state`)

| State Key | Written By | Read By | Purpose |
|---|---|---|---|
| `codebase_map` | `ingestion_agent` | `planning_agent`, experts | File tree, detected frameworks, file sizes |
| `governance_rules` | `confluence_rules_agent` | `governance_expert` | Live policies parsed from Confluence |
| `review_plan` | `planning_agent` | all experts | Structured assignment of modules & focus areas |
| `expert_findings_*` | each expert | `evaluation_expert`, `synthesis_agent` | Categorized findings and recommendations |
| `evaluation_grade` | `evaluation_expert` | `revision_agent`, frontend | Quality score (A-F) and iteration counter |
| `synthesis_report` | `synthesis_agent` | `metrics_agent`, `html_agent` | Comprehensive audit report in Markdown |
| `metrics_json` | `metrics_agent` | `html_agent`, frontend | Numeric scores, issue severities, Chart.js data |
| `html_report_artifact` | `html_agent` | API response / frontend | Standalone downloadable HTML audit report |
| `remediation_plan` | `remediation_agent` | frontend, SCM | Generated code patches and PR branches |

---

## 🛠️ Technical Stack

| Layer | Technology |
|---|---|
| **Agent Framework** | Google ADK 2.0+ (Agent Development Kit) |
| **Language & Runtime** | Python 3.13+ · Node.js 20+ |
| **LLM Models** | Gemini 3.1 Pro Preview · Gemini 3 Flash Preview · Gemini 3.1 Flash Lite |
| **Backend API** | FastAPI + Uvicorn (Universal ADK REST & SSE Stream Gateway) |
| **Frontend UI** | Next.js 16 (App Router) · React 19 · Tailwind CSS v4 · Framer Motion |
| **Brand & Design** | Agent Guardian Workspace · Inter Typography · Cobalt/Ice Blue Palette |
| **Static Analysis** | pyflakes · bandit |
| **Observability** | OpenTelemetry → Google Cloud Trace (Native ADK Telemetry) |
| **Artifacts Storage** | Google Cloud Storage (GCS `GcsArtifactService`) · Local `FileArtifactService` |
| **Session Persistence** | Vertex AI Agent Engine (`agentengine://`) · Local Memory/Filesystem |
| **SCM Integrations** | GitHub REST API · Bitbucket Cloud REST API |
| **Rules Sources** | Atlassian Confluence REST v2 + markdownify |
| **Deployment & CI/CD** | Google Artifact Registry · Google Cloud Run · Vertex AI Agent Engine · Docker |

---

## 📁 Project Structure

```
.
├── agent_guardian/              # ADK Agent Swarm Backend
│   ├── agent.py                 # root_agent + review_pipeline + ADK App config
│   ├── config.py                # Pydantic AgentSettings & model configuration
│   ├── state.py                 # Typed session state keys and models
│   ├── prompts.py               # Shared system instructions and templates
│   ├── sub_agents/              # Individual ADK Subagents
│   │   ├── ingestion_agent.py
│   │   ├── planning_agent.py
│   │   ├── adk_expert.py
│   │   ├── security_expert.py
│   │   ├── quality_expert.py
│   │   ├── governance_expert.py
│   │   ├── code_validator_agent.py
│   │   ├── evaluation_expert.py
│   │   ├── revision_agent.py
│   │   ├── synthesis_agent.py
│   │   ├── metrics_agent.py
│   │   ├── html_agent.py
│   │   ├── remediation_agent.py
│   │   ├── followup_agent.py
│   │   └── registry.py          # Dynamic agent registration
│   ├── tools/                   # Multi-SCM and analysis tools
│   │   ├── github_tool.py
│   │   ├── bitbucket_tool.py
│   │   ├── static_analysis_tool.py
│   │   ├── file_tool.py
│   │   ├── governance_tools.py
│   │   ├── artifact_tool.py
│   │   └── model_lifecycle_tool.py
│   ├── utils/                   # Resiliency, token budgets, caching
│   │   ├── resilience.py
│   │   ├── token_utils.py
│   │   ├── context_cache.py
│   │   ├── confluence_rest.py
│   │   └── tool_guards.py
│   ├── templates/               # Markdown prompts & HTML vendor assets
│   └── skills/                  # Extensible domain audit skill packs
│
├── api/                         # FastAPI Application Gateway
│   └── main.py                  # ADK App Router, /list-apps, SSE streaming, /healthz
│
├── frontend/                    # Modern Next.js 16 Web Dashboard
│   ├── app/                     # App Router pages & API proxy
│   │   ├── page.tsx             # Agent Guardian workspace & agent chat
│   │   ├── review/[sessionId]/  # Dedicated live review stream view
│   │   ├── results/[sessionId]/ # Historical and completed report view
│   │   └── api/adk/[...path]/   # Universal ADK upstream proxy
│   ├── components/              # Modular UI Components
│   │   ├── guardian/            # GuardianHeader with App Switcher, GuardianSidebar, ExportShareModal
│   │   ├── review/              # ChatLogRow, ToolCallView, UserTraceBar, AuditSearchModal
│   │   ├── console/             # Mission Control Console Drawer
│   │   ├── brand/               # Agent Guardian Vector Logo & Theme
│   │   └── adk/                 # Embeddable ADKAgentChat component
│   ├── hooks/                   # useAgentReview, useTheme hooks
│   ├── lib/                     # adk-client, event-parser, session utils
│   └── types/                   # Universal ADK and Review TypeScript types
│
├── docs/                        # Architecture & Implementation Specs
│   ├── ADK_ARCHITECTURE_DESIGN.md
│   ├── production_architecture.md
│   └── changes.md
│
└── tests/                       # Test Suites
    ├── unit/
    └── integration/
```

---

## 🚀 Getting Started

### Prerequisites

- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Python 3.13+
- Node.js 20+
- Google Cloud Project with Vertex AI API enabled

### Installation

```bash
# Install backend dependencies
make install

# Install all dependencies (Backend + Frontend)
make install-all
```

### Environment Configuration

Create a `.env` file in the root directory:

```bash
# Google Cloud & Vertex AI
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Model Settings (Optional - sensible defaults in config.py)
ROOT_MODEL=gemini-3.1-flash-lite-preview
EXPERT_MODEL=gemini-3-flash-preview
GOVERNANCE_MODEL=gemini-3.1-pro-preview

# Observability & Distributed Tracing (Google Cloud Trace via OpenTelemetry)
ENABLE_CLOUD_TRACING=true
OTEL_SERVICE_NAME=agent-guardian
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_agent_spans
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=true

# Production Artifacts & Session Persistence (GCS & Vertex AI)
ARTIFACT_SERVICE_URI=gs://agentguardian-prod-artifacts
SESSION_SERVICE_TYPE=vertexai

# SCM Credentials (Optional for automated PRs)
GITHUB_TOKEN=ghp_...
BITBUCKET_TOKEN=...
BITBUCKET_WORKSPACE=...

# Confluence Governance Integration (Optional)
ATLASSIAN_API_TOKEN=...
ATLASSIAN_URL=https://yourorg.atlassian.net
ATLASSIAN_USER_EMAIL=user@company.com
```

### Running Locally

```bash
# Run backend (:8000) and frontend (:3000) concurrently:
make dev

# Or on Windows PowerShell:
.\dev.ps1

# Or on Windows CMD:
dev.bat
```

Open [http://localhost:3000](http://localhost:3000) to access the Agent Guardian workspace.

---

## 🚢 Production Deployment

### 1. Build & Push to Google Artifact Registry

```bash
# Authenticate Docker to Google Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build & Push Backend Container
docker build -t us-central1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/agent-guardian/backend:latest .
docker push us-central1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/agent-guardian/backend:latest
```

### 2. Deploy to Google Cloud Run

```bash
# Deploy backend service to Cloud Run with GCS Artifacts and Cloud Trace enabled
make deploy-backend
```

### 3. Deploy to Vertex AI Agent Engine

```bash
# Deploy directly to Vertex AI Reasoning Engines (ADK App runtime)
make deploy-agent-engine
```

---

## 🧪 Testing & Verification

```bash
# Run unit test suite
make test

# Run integration tests
make test-integration

# Run full pre-commit validation (format + lint + security + tests)
make check
```

---

## 📄 License & Support
For questions, support, or contributions, contact [sharmaasharmaa50@gmail.com]

