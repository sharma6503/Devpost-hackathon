# Agent Guardian — Web Workspace & Universal ADK Dashboard

The official web frontend for **Agent Guardian**, featuring a modern responsive multi-device layout, tailored brand visual design, and universal compatibility with **any Google Agent Development Kit (ADK 2.0+)** backend.

---

## 🌟 Key Features

* **Universal Google ADK Connectivity:** Connects natively to `agent_guardian` and **any custom ADK agent backend**. Features automatic dynamic app discovery (`GET /list-apps`), upstream header proxying (`x-adk-base-url`), and per-app session persistence.
* **Agent Guardian Workspace & Responsive UI:** Clean sidebar navigation with collapsible session history, sticky header with active repository indicators, multi-line auto-growing prompt bar, sample query cards, and smooth dark/light theme switching.
* **Interactive Tool & Thought Visualizations:**
  * **`ThoughtView`**: Collapsible chain-of-thought and reasoning process cards.
  * **`ToolCallView`**: Live visualization of tool invocations, function arguments with JSON inspector, and execution status.
  * **`ToolResultView`**: Collapsible emerald preview cards showing tool return values.
* **Real-Time SSE Pipeline Streaming:** Live Server-Sent Events (SSE) streaming of token consumption, agent handoffs, phase transitions, and state deltas.
* **Mission Control Console Drawer:** Expandable real-time drawer providing:
  * **Raw Event Inspector**: Deep-dive into raw ADK SSE events with search and JSON tree view.
  * **State Viewer**: Live inspection of `ctx.session.state` (codebase map, review plan, metrics).
  * **Telemetry Cards**: Live token count counters and agent execution latency.
  * **Artifact Browser**: Instant preview and download of generated reports and diffs.
* **Automated Remediation & HITL Review:** Side-by-side git diff preview with one-click automated PR creation to GitHub / Bitbucket.
* **Interactive Follow-Up Agent:** Chat with `followup_agent` to query findings, request architectural clarifications, or generate code snippets without re-running the entire pipeline.
* **Standalone `<ADKAgentChat />` Component:** Zero-friction embeddable React component to plug any ADK agent into any page.

---

## 🎨 Brand Design Tokens

Agent Guardian implements a tailored visual identity based on the brand vector assets:
- **Primary Cobalt:** `#2525A3`
- **Ice Blue Accents:** `#A6C3EE` / `#3B3BE8`
- **Deep Midnight Navy:** `#0E1F3D`
- **Dark Canvas / Sidebar:** `#212121` / `#171717`
- **Typography:** `Inter`, `Segoe UI`, and `Fira Code` for monospace snippets

---

## 🛠️ Tech Stack

* **Framework:** [Next.js 16 (App Router)](https://nextjs.org/) + React 19
* **Styling:** [Tailwind CSS v4](https://tailwindcss.com/)
* **Icons & Animation:** [Lucide React](https://lucide.dev/), [Framer Motion](https://www.framer.com/motion/)
* **Charts & Visuals:** Chart.js + Canvas Confetti
* **Communication:** Server-Sent Events (SSE) & Universal REST API proxy via `/app/api/adk/[...path]/route.ts`

---

## 📦 Getting Started

### Prerequisites

* Node.js 20+
* Backend FastAPI / ADK server running on `http://localhost:8000` (or configured via environment)

### Installation

```bash
cd frontend
npm install
```

### Environment Configuration

Create a `.env.local` in `frontend/` (optional for local development; defaults to `http://127.0.0.1:8000`):

```env
# Backend API Target URL
NEXT_PUBLIC_API_URL=http://localhost:8000

# Default ADK Application Name (optional, defaults to agent_guardian)
NEXT_PUBLIC_ADK_APP_NAME=agent_guardian
```

### Running Locally

```bash
# Start development server with hot-reload (:3000)
npm run dev

# Build production bundle
npm run build

# Start production server (:3000)
npm start
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🔌 Universal ADK Integration & Component Usage

### Using the Embeddable ADK Component
You can embed any Google ADK agent directly into any React page:

```tsx
import { ADKAgentChat } from "@/components/adk/ADKAgentChat";

export default function CustomAgentPage() {
  return (
    <div className="h-screen w-full">
      <ADKAgentChat
        appName="code_refactor_agent"
        agentTitle="Code Refactor Assistant"
        placeholder="Ask the refactor agent to optimize a function..."
      />
    </div>
  );
}
```

### Universal ADK Proxy Endpoints
The frontend exposes a universal proxy route at `/api/adk/[...path]` that transparently routes requests to upstream ADK servers while supporting custom target URLs via the `x-adk-base-url` header:
- `GET /api/adk/list-apps` — Discovers all active apps on the ADK server
- `POST /api/adk/apps/{appName}/users/{userId}/sessions/{sessionId}` — Creates a session
- `GET /api/adk/apps/{appName}/users/{userId}/sessions/{sessionId}` — Fetches session state
- `POST /api/adk/run_sse` — Initiates real-time SSE execution stream

---

## 📁 Project Structure

```
frontend/
├── app/
│   ├── api/adk/[...path]/    # Universal ADK reverse proxy route
│   ├── api/auth/login/       # Basic authentication session endpoint
│   ├── results/[sessionId]/  # Historical and completed audit results view
│   ├── review/[sessionId]/   # Active audit progress and live streaming page
│   ├── layout.tsx            # Global layout wrapper with theme & auth providers
│   ├── page.tsx              # Agent Guardian workspace, prompt bar & agent chat
│   └── globals.css           # Global Tailwind CSS tokens & theme variables
├── components/
│   ├── adk/                  # Embeddable ADKAgentChat standalone component
│   ├── brand/                # Vector Brand Logo, Theme Provider & Toggle
│   ├── guardian/             # GuardianHeader with ADK App selector, GuardianSidebar, ExportShareModal
│   ├── console/              # Mission Control Drawer (Raw events, telemetry, state)
│   ├── review/               # ChatLogRow (Tool calls, results, thoughts), UserTraceBar
│   └── results/              # Metrics charts, remediation diff review modal
├── hooks/                    # useAgentReview, useTheme custom React hooks
├── lib/                      # adk-client, event-parser, session utils
├── types/                    # Universal ADK, Gemini parts & review types
└── package.json
```

