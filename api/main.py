"""
Agent Guardian API service.

Serves the ADK API the Next.js frontend already proxies to
(frontend/app/api/adk/[...path]/route.ts → ADK_BASE_URL):

  POST/GET/DELETE /apps/{app}/users/{user}/sessions[/{id}]   session CRUD
  GET  /apps/{app}/users/{user}/sessions/{id}/artifacts[...] report artifacts
  POST /run_sse                                              SSE review stream
  GET  /list-apps

Built with ADK's own `get_fast_api_app` (the same app `adk api_server` runs)
so the event/session wire contract always matches the installed ADK version —
plus a couple of operational endpoints (/healthz, /).

Run locally:
    uvicorn api.main:app --port 8000
Docker/Cloud Run can use this as an alternative to `adk web` when the
operator UI isn't needed.
"""

from __future__ import annotations

import logging
import os
from dotenv import load_dotenv

# Load environment variables eagerly before any other imports are resolved
load_dotenv(override=True)

# Clear process-level GOOGLE_API_KEY if Enterprise / Vertex AI is active to prevent auth collisions
use_enterprise = (
    os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("1", "true", "yes")
    or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
)
if use_enterprise:
    os.environ.pop("GOOGLE_API_KEY", None)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Event-loop / subprocess compat (Windows Proactor policy for MCP) must be in
# place before ADK spins up runners. Idempotent.
from agent_guardian.utils.compat import setup_platform_compat

setup_platform_compat()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    userId: str
    department: str
    country: str


logger = logging.getLogger("uvicorn")

# agents_dir is the directory CONTAINING the agent package (repo root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("API_ALLOW_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]

app: FastAPI


def _build_app() -> FastAPI:
    from google.adk.cli.fast_api import get_fast_api_app
    from agent_guardian.utils.session_factory import _ensure_gcp_env_vars

    _ensure_gcp_env_vars()

    session_uri = os.environ.get("SESSION_SERVICE_URI")
    if not session_uri and os.environ.get("SESSION_SERVICE_TYPE", "").strip().lower() in ("vertexai", "agentengine"):
        session_uri = "agentengine://"

    adk_app = get_fast_api_app(
        agents_dir=_REPO_ROOT,
        web=False,  # API only; the frontend is the UI
        allow_origins=_ALLOW_ORIGINS,
        session_service_uri=session_uri or None,
        artifact_service_uri=os.environ.get("ARTIFACT_SERVICE_URI") or None,
        otel_to_cloud=False,
        auto_create_session=True,
    )
    adk_app.title = "Agent Guardian API"
    adk_app.description = (
        "ADK session/run API for the Agent Guardian audit pipeline. "
        "Consumed by the Next.js frontend via its /api/adk proxy."
    )

    @adk_app.get("/healthz", tags=["ops"])
    async def healthz() -> dict:
        return {"status": "ok", "app": "agent_guardian"}

    @adk_app.post("/auth/login", tags=["auth"], response_model=LoginResponse)
    async def login(body: LoginRequest) -> LoginResponse:
        from fastapi.concurrency import run_in_threadpool

        from agent_guardian.auth import verify_credentials

        # verify_credentials does a blocking BigQuery query + CPU-bound bcrypt
        # verify; run it off the event loop so concurrent requests (incl. SSE
        # audit streams) aren't stalled for the login's duration.
        user = await run_in_threadpool(verify_credentials, body.username.strip(), body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        return LoginResponse(**user)

    @adk_app.get("/", tags=["ops"])
    async def root() -> dict:
        return {
            "service": "agent-guardian-api",
            "docs": "/docs",
            "health": "/healthz",
        }

    return adk_app


app = _build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["agent_guardian", "api"],
    )
