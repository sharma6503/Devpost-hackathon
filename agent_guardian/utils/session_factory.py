from __future__ import annotations

"""
Session Factory for Agent Guardian.

Provides a unified factory to initialize ADK SessionServices based on environment
configuration (Vertex AI Session Service, Database, or InMemory fallback).
"""

import logging
import os

from google.adk.sessions import (
    BaseSessionService,
    InMemorySessionService,
)

logger = logging.getLogger(__name__)


def _ensure_gcp_env_vars(project_id: str | None = None, location: str | None = None) -> tuple[str, str]:
    """Ensures GCP project and session location environment variables are populated.

    Allows GOOGLE_CLOUD_LOCATION=global for Gemini model calls, while resolving
    a regional location for Vertex AI Session Service via SESSION_LOCATION or
    GOOGLE_CLOUD_AGENT_ENGINE_LOCATION (defaulting to us-central1).
    """
    proj = (
        project_id
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    )
    if not proj:
        try:
            import google.auth

            _, default_proj = google.auth.default()
            if default_proj:
                proj = default_proj
        except Exception:
            pass

    if not proj:
        proj = "enterprise-ai-guardian"

    session_loc = (
        location
        or os.environ.get("SESSION_LOCATION")
        or os.environ.get("SESSION_SERVICE_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION")
    )

    if not session_loc:
        g_loc = os.environ.get("GOOGLE_CLOUD_LOCATION")
        if g_loc and g_loc.lower() != "global":
            session_loc = g_loc
        else:
            session_loc = "us-central1"

    os.environ["GOOGLE_CLOUD_PROJECT"] = proj
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ["SESSION_LOCATION"] = session_loc
    os.environ["GOOGLE_CLOUD_AGENT_ENGINE_LOCATION"] = session_loc

    return proj, session_loc


def get_session_service(
    service_type: str | None = None,
    service_uri: str | None = None,
    project_id: str | None = None,
    location: str | None = None,
    agent_engine_id: str | None = None,
) -> BaseSessionService:
    """Instantiates and returns an ADK SessionService based on configuration.

    Selection priority:
    1. If `service_type` is 'vertexai' or `SESSION_SERVICE_TYPE=vertexai` or `service_uri` starts with
       'vertexai://' or 'agentengine://': instantiates `VertexAiSessionService`.
    2. If `service_uri` or `SESSION_SERVICE_URI` is provided (e.g. 'sqlite:///', 'postgresql://...'):
       instantiates `DatabaseSessionService`.
    3. Default fallback: instantiates `InMemorySessionService`.
    """
    resolved_type = service_type or os.environ.get("SESSION_SERVICE_TYPE", "").strip().lower()
    resolved_uri = service_uri or os.environ.get("SESSION_SERVICE_URI", "").strip()

    # Vertex AI Session Service explicit or URI trigger
    is_vertex = (
        resolved_type == "vertexai"
        or resolved_type == "agentengine"
        or resolved_uri.startswith("vertexai://")
        or resolved_uri.startswith("agentengine://")
    )

    if is_vertex:
        try:
            proj, loc = _ensure_gcp_env_vars(project_id, location)

            from google.adk.sessions import VertexAiSessionService

            # Extract agent_engine_id from URI if provided like agentengine://my-engine-id
            engine_id = agent_engine_id or os.environ.get("AGENT_ENGINE_ID") or os.environ.get("VERTEX_AGENT_ENGINE_ID")
            if not engine_id and resolved_uri.startswith(("agentengine://", "vertexai://")):
                parts = resolved_uri.split("://", 1)
                if len(parts) > 1 and parts[1]:
                    engine_id = parts[1].strip("/")

            logger.info(
                "Initializing VertexAiSessionService (project=%s, location=%s, agent_engine_id=%s)",
                proj,
                loc,
                engine_id,
            )
            return VertexAiSessionService(
                project=proj,
                location=loc,
                agent_engine_id=engine_id or None,
            )
        except Exception as e:
            logger.error(
                "Failed to initialize VertexAiSessionService (%s). Falling back to InMemorySessionService.",
                e,
                exc_info=True,
            )
            return InMemorySessionService()

    # Database Session Service if a database URI is supplied
    if resolved_uri and not is_vertex:
        try:
            from google.adk.sessions.database_session_service import (
                DatabaseSessionService,
            )

            logger.info("Initializing DatabaseSessionService (uri=%s)", resolved_uri)
            return DatabaseSessionService(db_url=resolved_uri)
        except Exception as e:
            logger.error(
                "Failed to initialize DatabaseSessionService (%s). Falling back to InMemorySessionService.",
                e,
                exc_info=True,
            )
            return InMemorySessionService()

    logger.info("Using default InMemorySessionService.")
    return InMemorySessionService()
