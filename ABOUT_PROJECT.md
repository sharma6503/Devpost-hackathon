# 🛡️ Agent Guardian: About the Project

---

## 🏷️ Taglines & Elevator Pitch

* **Primary Tagline:** Autonomous Enterprise Multi-Agent Code Auditing, Governance, and Self-Healing Remediation.
* **30-Second Elevator Pitch:**  
  *Agent Guardian is an enterprise multi-agent code auditing and self-healing platform built on Google ADK (2.0+) and Vertex AI Gemini. Instead of slow manual reviews or fragmented static linters, Agent Guardian orchestrates specialized AI domain experts through an autonomous Critic loop. It performs deep static analysis, validates live organizational policies from Confluence, generates executive scorecards, and autonomously creates verified remediation Pull Requests on GitHub and Bitbucket with human-in-the-loop approval.*

---

## 🏆 Hackathon Track Alignment (*All Things Agentic Hackathon*)

* **Primary Track:** **The Fortified Enterprise Fleet**
* **Secondary / Focus Area:** **The Taskmaster**
* **Track Justification:**  
  Agent Guardian is engineered specifically for enterprise zero-trust security, dynamic policy governance, and resilient multi-agent execution. Rather than operating as an isolated chatbot, it deploys a fleet of specialized domain agents that dynamically fetch organizational compliance rules from Confluence, audit code with deterministic static analysis tools (`bandit`, `pyflakes`), subject findings to an independent Critic evaluator, and execute verified git remediation PRs with strict scope isolation and Human-in-the-Loop safeguards.

---

## 💡 Inspiration

In modern software engineering, code reviews are the primary defense against security vulnerabilities, performance regressions, and architectural decay. However, as engineering organizations scale and release cycles accelerate, traditional code reviews face two critical bottlenecks:

1. **Human Fatigue & Cognitive Fragmentation:** Security engineers, architects, and compliance officers review code in isolation, often missing cross-cutting governance rules or subtle vulnerabilities buried across thousands of lines of changes.
2. **The "Actionability Gap":** Traditional linters and security scanners produce exhaustive lists of static warnings without contextual understanding or automated fixes, leaving developers with the tedious burden of manual remediation.

We asked ourselves: **What if a team of specialized AI agents could collaborate like a senior engineering staff council — rigorously inspecting code, dynamically auditing against company-specific governance policies from Confluence, critiquing each other’s findings in an autonomous quality loop, and autonomously opening verified remediation Pull Requests?**

That vision led to the creation of **Agent Guardian**.

---

## 🌟 What It Does

Agent Guardian transforms codebase auditing and compliance into an autonomous, self-healing pipeline:

* **Universal Google ADK Agent Workspace:** A modern, responsive web workspace (Next.js 16 + React 19) that connects out-of-the-box to `agent_guardian` and **any** Google ADK agent application via dynamic app discovery (`GET /list-apps`) and header proxying (`x-adk-base-url`).
* **Multi-Agent Expert Council:** Parallelized domain agents perform in-depth analysis across **ADK Best Practices** (`adk_expert`), **OWASP Security** (`security_expert`), **Code Quality** (`quality_expert`), **Architecture** (`architecture_expert`), and **Governance** (`governance_expert`).
* **Dynamic Confluence Governance Sync:** Dynamically crawls organizational security, compliance, and architectural policies from Atlassian Confluence spaces and skill registries to audit code against live corporate guidelines.
* **Deterministic Static Pre-Pass:** Ingests local repository archives or Git branches, executing deterministic static analysis (`pyflakes`, `bandit`) and parsing codebase ASTs before LLM evaluation.
* **Evaluator-Critic Quality Gate (`LoopAgent`):** An independent evaluation agent grades comprehensive findings (`A` to `F`). If a review fails to meet quality standards, the pipeline dynamically loops back to refine the weakest agent's output before synthesis.
* **Autonomous Remediation & HITL PRs:** Writes unified git diff patches and integrates with GitHub and Bitbucket REST APIs to open automated Pull Requests once approved by the auditor.
* **Mission Control Console Drawer:** Real-time observability dashboard featuring raw ADK event inspection, token consumption telemetry, live state trees (`ctx.session.state`), and downloadable HTML audit dossiers.
* **Executive Dashboard Reports:** Generates zero-dependency, standalone HTML/Chart.js audit dossiers ready for executive review.

---

## 🏗️ How We Built It

Agent Guardian is built from the ground up as a cloud-native, enterprise-grade multi-agent platform powered by the **Google Agent Development Kit (ADK 2.0+)** and **Vertex AI Gemini** models.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Agent Guardian Architecture                           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        ▼                                                             ▼
┌──────────────────────────────┐                            ┌──────────────────────────────┐
│   Universal ADK Workspace    │  ◄── SSE Stream & Proxy ──►│    ADK Multi-Agent Pipeline   │
│  Next.js 16 • React 19       │                            │  • Ingestion & AST Parser    │
│  • Live Thought Telemetry    │                            │  • Dynamic Confluence Rules  │
│  • Tool Call Inspector       │                            │  • Specialized Reviewers     │
│  • Mission Control Drawer    │                            │  • Evaluator-Critic Gate     │
│  • 1-Click PR Approvals      │                            │  • Automated Remediation PR  │
└──────────────────────────────┘                            └──────────────────────────────┘
                                                              │
                                     ┌────────────────────────┴────────────────────────┐
                                     ▼                                                 ▼
                          ┌─────────────────────┐                           ┌─────────────────────┐
                          │   Vertex AI Gemini  │                           │  Google Cloud Run   │
                          │ • Context Caching   │                           │ • Cloud Trace (OTel)│
                          │ • Gemini 3.7 Flash  │                           │ • GCS Artifacts     │
                          └─────────────────────┘                           └─────────────────────┘
```

### 1. Multi-Agent Pipeline Topology (`agent_guardian/agent.py`)
We architected a hierarchical multi-agent workflow orchestrated by an ADK Supervisor:
* **Ingestion & Static Pre-Pass (`ingestion_agent`):** Clones Git repositories or extracts ZIP archives, runs `pyflakes` and `bandit`, and generates the file tree and framework map.
* **Dynamic Governance Crawling (`confluence_rules_agent`):** Connects to Confluence REST APIs to extract live organizational coding, security, and architectural policies.
* **Specialized Expert Council:** Parallelized domain specialists inspect the codebase across ADK architecture, security, quality, governance, and code validity.
* **Evaluator-Critic Quality Gate (`evaluation_agent` & `revision_agent`):** An independent evaluation agent scores findings against rubric standards. If score < threshold, it iterates and commands targeted revisions.
* **Synthesis & Metrics (`synthesis_agent`, `metrics_agent`, `html_agent`):** Aggregates findings into unified executive markdown reports, structured JSON scorecards, and standalone interactive HTML dashboards.
* **Autonomous Remediation (`remediation_agent`):** Formulates code repair diffs, verifies them against live model catalogs (`get_model_lifecycle`), and creates Git branches and PRs on GitHub and Bitbucket.

### 2. Universal Real-Time Web Workspace (`frontend/`)
* **Next.js 16 (Turbopack) & React 19:** Optimized for performance and real-time Server-Sent Events (SSE) consumption.
* **Live Thought & Tool Telemetry:** Native visual rendering of reasoning chains (`thought`), tool calls with JSON argument inspection, and tool responses with zero perceived latency.
* **Dynamic Upstream Discovery:** Dynamically detects backend ADK applications (`GET /list-apps`) and proxies upstream sessions (`x-adk-base-url`), making the frontend compatible with any ADK agent application.

### 3. Performance & Token Optimization
* **Vertex AI Context Caching (`ContextCacheConfig`):** Caches large repository AST maps and Confluence governance rules (`min_tokens=15000`, `ttl=3600s`), slashing repetitive token costs by up to **90%**.
* **ADK Events Compaction (`EventsCompactionConfig`):** Automatically compacts conversation history between iterative Critic cycles to prevent context window saturation.
* **Enterprise Observability:** Emits distributed trace spans to **Google Cloud Trace** via OpenTelemetry (`opentelemetry-exporter-gcp-trace`) implementing `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_agent_spans`.

---

## 🧠 Model Configuration & Strategy

In `agent_guardian/config.py`, **all agent tiers are standardized on `gemini-3.7-flash` as the default model family**. This architectural decision delivers sub-second latency, high token throughput, native structured output, and reliable tool calling across the entire multi-agent fleet.

Every model tier can also be individually overridden at runtime via environment variables:

| Agent Tier | Default Model | Config Field / Env Var Override | Key Responsibility |
|---|---|---|---|
| **Root Supervisor** | `gemini-3.7-flash` | `ROOT_MODEL` | User intent routing, task dispatch, and session coordination. |
| **Ingestion Agent** | `gemini-3.7-flash` | `INGESTION_MODEL` | AST mapping, framework detection, and file structure analysis. |
| **ADK Expert** | `gemini-3.7-flash` | `ADK_EXPERT_MODEL` | Google ADK patterns, state contracts, and live model lifecycle audits. |
| **Security Expert** | `gemini-3.7-flash` | `SECURITY_MODEL` | OWASP vulnerabilities, secret leaks, and least-privilege analysis. |
| **Quality Expert** | `gemini-3.7-flash` | `QUALITY_MODEL` | Code smells, dead code, complexity, and typing validation. |
| **Governance Expert** | `gemini-3.7-flash` | `GOVERNANCE_MODEL` | Confluence corporate policy compliance (overridable to Pro for complex policies). |
| **Code Validator** | `gemini-3.7-flash` | `VALIDATOR_MODEL` | Static analysis verification against `bandit` and `pyflakes` logs. |
| **Evaluator-Critic Gate** | `gemini-3.7-flash` | `EVALUATION_MODEL` | Deterministic rubric grading (A–F, 0–10) and revision commands. |
| **Synthesis Agent** | `gemini-3.7-flash` | `SYNTHESIS_MODEL` | Comprehensive executive markdown narrative report compilation. |
| **Metrics Agent** | `gemini-3.7-flash` | `METRICS_MODEL` | Structured JSON extraction for Chart.js dashboard integration. |
| **Executive HTML Agent** | `gemini-3.7-flash` | `HTML_MODEL` | Standalone, 30–40 KB zero-dependency HTML dashboard generation. |
| **Remediation Agent** | `gemini-3.7-flash` | `REMEDIATION_MODEL` | Unified git diff synthesis and automated PR creation (temp: 0.2). |
| **Follow-Up Agent** | `gemini-3.7-flash` | `FOLLOWUP_MODEL` | Interactive post-audit Q&A and findings exploration. |

### Sampling Temperature Matrix
* `remediation_temperature = 0.2`: Ensures precise, reproducible git diffs and correct tool parameters.
* `evaluation_temperature = 0.2`: Enforces deterministic grading against audit rubrics.
* `metrics_temperature = 0.2`: Guarantees schema-compliant JSON extraction.
* `html_temperature = 0.3`: Generates clean, valid standalone HTML/CSS documents.
* `synthesis_temperature = 0.7`: Produces fluent, comprehensive executive summary narratives.

---

## ⚔️ Challenges We Faced

1. **Preventing LLM Hallucinations on Large Repositories:**  
   Feeding raw monolithic codebases into LLMs caused token saturation and context drift. We solved this by implementing an AST module mapper that categorizes files into logic, configuration, and documentation, combined with **Vertex AI Context Caching** to reduce token overhead by up to 90%.

2. **Managing Multi-Agent Convergence & Quality Loops:**  
   Early prototypes occasionally entered redundant review loops. We designed a deterministic **Evaluator-Critic Gate** with strict convergence bounds, state compaction (`EventsCompactionConfig`), and fallback synthesis thresholds to ensure high-grade audit output without infinite execution loops.

3. **Real-Time Streaming of Complex Multi-Turn Tool Payloads:**  
   Handling parallel function calls, thoughts, and partial SSE chunks across heterogeneous ADK agents required a robust parsing engine. We developed an idempotent state-reduction parser on the frontend that seamlessly reconstitutes split Markdown deltas, JSON function arguments, and nested execution errors.

4. **Safe Automated Git Remediation:**  
   Blindly applying AI code modifications risks breaking builds. We introduced a **Human-in-the-Loop approval gate** where remediation diffs are pre-visualized in side-by-side split editors with one-click approval before any branch creation or Pull Request dispatch occurs.

---

## 🏆 Accomplishments That We're Proud Of

* Built an end-to-end autonomous multi-agent pipeline using Google ADK 2.0+ that takes a repository URL, validates it against live Confluence policies, and produces a verified, self-healing Pull Request.
* Achieved **~90% token cost reduction** during iterative audit passes using Vertex AI Context Caching.
* Created a **Universal ADK Workspace** that connects to and visualizes any Google ADK agent application.
* Designed a zero-dependency, standalone executive HTML dashboard artifact with embedded interactive charts.

---

## 🧠 What We Learned

* **The Power of Google ADK’s State Model:** Centralized session state (`ctx.session.state`) combined with event compaction and resumability dramatically simplifies building resilient, multi-turn AI systems compared to ad-hoc framework setups.
* **Multi-Agent Specialization Beats Monolithic Prompts:** Dividing code review into targeted domains (governance vs. static analysis vs. security) with an independent Critic evaluator delivers significantly higher signal-to-noise ratios and actionable recommendations.
* **Transparency Builds Developer Trust:** Showing the agent's step-by-step reasoning chain (`thought`), tool telemetry, and exact diff rationale turns AI from an unpredictable black box into a trusted, collaborative peer reviewer.

---

## 🚀 What's Next for Agent Guardian

* **CI/CD Native GitHub Action & Bitbucket Pipe:** One-click integration into CI/CD build pipelines to block failing pull requests automatically.
* **IDE Extension (VS Code / JetBrains):** In-editor companion sidebar for instant local file auditing before staging commits.
* **Multi-Repo Dependency Auditing:** Cross-repository architectural dependency graph analysis for enterprise microservices.

---

## 🧪 Try It Out / Testing Instructions for Judges

### 1. Prerequisites
- Python 3.13+ with `uv` package manager (`pip install uv`)
- Node.js 20+ & npm
- Google Cloud Project with Vertex AI API enabled

### 2. Setup & Run Locally
```bash
# Clone the repository
git clone <YOUR_REPO_URL>
cd agent-guardian

# Install all dependencies (Backend + Frontend)
make install-all

# Configure environment variables
cp .env.example .env
# Set GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION

# Start the application locally
# Linux/macOS:
make dev
# Windows PowerShell:
.\dev.ps1
# Windows CMD:
dev.bat
```

### 3. Open Web Workspace
Navigate to `http://localhost:3000` in your browser. Select **agent_guardian** from the application switcher to start an audit and experience the live multi-agent workflow.

---

## 🛠️ Built With Tags
`google-adk`, `vertex-ai`, `gemini-3.7-flash`, `gemini-3.1-pro`, `python`, `fastapi`, `nextjs-16`, `react-19`, `typescript`, `tailwindcss`, `google-cloud-run`, `google-cloud-storage`, `google-cloud-trace`, `opentelemetry`, `github-api`, `bitbucket-api`, `confluence-api`, `docker`, `bandit`, `pyflakes`

