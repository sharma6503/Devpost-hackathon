# 🛡️ Agent Guardian: About the Project

---

## 🏷️ Taglines & Elevator Pitch

* **Primary Tagline:** Autonomous Multi-Agent Code Auditing, Governance, and Self-Healing Remediation.
* **30-Second Elevator Pitch:**  
  *Agent Guardian is an enterprise multi-agent code auditing and self-healing platform built on Google ADK (2.0+) and Vertex AI Gemini. Instead of slow manual reviews or fragmented static linters, Agent Guardian orchestrates specialized AI domain experts through an autonomous Critic loop. It performs deep static analysis, validates live organizational policies from Confluence, generates executive scorecards, and autonomously creates verified remediation Pull Requests on GitHub and Bitbucket with human-in-the-loop approval.*

---

## 💡 Inspiration

In modern software engineering, code reviews are the primary defense against security vulnerabilities, performance regressions, and architectural decay. However, as engineering organizations scale and release cycles accelerate, traditional code reviews face two critical bottlenecks:

1. **Human Fatigue & Cognitive Fragmentation:** Security engineers, architects, and compliance officers review code in isolation, often missing cross-cutting governance rules or subtle vulnerabilities buried across thousands of lines of changes.
2. **The "Actionability Gap":** Traditional linters and security scanners produce exhaustive lists of static warnings without contextual understanding or automated fixes, leaving developers with the tedious burden of manual remediation.

We asked ourselves: **What if a team of specialized AI agents could collaborate like a senior engineering staff council — rigorously inspecting code, dynamically auditing against company-specific governance policies, critiquing each other’s findings, and autonomously opening verified remediation Pull Requests?**

That vision led to the creation of **Agent Guardian**.

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
```

### 1. Multi-Agent Pipeline Topology (`agent_guardian/agent.py`)
We architected a hierarchical multi-agent workflow orchestrated by an ADK Supervisor:
* **Ingestion & Static Pre-Pass (`ingestion_agent`):** Ingests local repository archives, GitHub repositories, or Bitbucket branches, executing deterministic static analysis (`pyflakes`, `bandit`) and parsing codebase architecture before LLM consumption.
* **Dynamic Governance Crawling (`confluence_rules_agent`):** Integrates with Atlassian Confluence APIs and GCP Skill Registries to inject live organizational security and architecture policies directly into review context.
* **Specialized Expert Council:** Parallelized domain agents perform in-depth analysis across **Security** (`security_expert`), **Code Quality** (`code_quality_expert`), **Architecture** (`architecture_expert`), and **Governance** (`governance_expert`).
* **Evaluator-Critic Quality Gate (`evaluation_agent`):** An independent evaluation agent grades the comprehensive findings (`A` to `F`). If a review fails to meet quality standards, the pipeline dynamically loops back to refine the weakest agent's output before synthesis.
* **Autonomous Remediation & Human-in-the-Loop PRs (`remediation_agent`):** The remediation agent writes unified git diff patches and integrates with GitHub and Bitbucket REST APIs to open automated Pull Requests once approved by the auditor.

### 2. Universal Real-Time Web Workspace (`frontend/`)
We built a modern, responsive web workspace using **Next.js 16 (Turbopack)** and **React 19**:
* **Live ADK Event Streaming:** Consumes Server-Sent Events (SSE) to render agent reasoning (`thought`), tool invocations, execution arguments, and results with zero perceived latency.
* **Universal ADK Connectivity:** Features dynamic application discovery (`GET /list-apps`) and header proxying (`x-adk-base-url`), allowing the frontend to connect to **any** Google ADK agent application out-of-the-box.
* **Mission Control Drawer & Event Inspector:** Empowers auditors to inspect live state trees (`ctx.session.state`), raw SSE events, latency metrics, and downloadable standalone HTML audit dossiers.

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

## 🧠 What We Learned

* **The Power of Google ADK’s State Model:** Centralized session state (`ctx.session.state`) combined with event compaction and resumability dramatically simplifies building resilient, multi-turn AI systems compared to ad-hoc LangChain or raw API setups.
* **Multi-Agent Specialization Beats Monolithic Prompts:** Dividing code review into targeted domains (governance vs. static analysis vs. security) with an independent Critic evaluator delivers significantly higher signal-to-noise ratios and actionable recommendations.
* **Transparency Builds Developer Trust:** Showing the agent's step-by-step reasoning chain (`thought`), tool telemetry, and exact diff rationale turns AI from an unpredictable black box into a trusted, collaborative peer reviewer.

---

## 🚀 What's Next for Agent Guardian

* **CI/CD Native GitHub Action & Bitbucket Pipe:** One-click integration into CI/CD build pipelines to block failing pull requests automatically.
* **IDE Extension (VS Code / JetBrains):** In-editor companion sidebar for instant local file auditing before staging commits.
* **Multi-Repo Dependency Auditing:** Cross-repository architectural dependency graph analysis for enterprise microservices.
