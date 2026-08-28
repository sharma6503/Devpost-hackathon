from __future__ import annotations

"""
Google Cloud Trace & OpenTelemetry Instrumentation for Agent Guardian.

Configures Google Cloud Trace exporters via Google ADK's telemetry framework.
Captures hierarchical spans for:
- Agent lifecycle and invocations (invoke_agent)
- Workflow orchestrations (invoke_workflow)
- Gemini model reasoning and generation (generate_content)
- Tool and MCP executions (execute_tool)
"""

import os
import logging

logger = logging.getLogger("agent_guardian.telemetry")


def is_cloud_tracing_enabled() -> bool:
    """Returns True if Cloud Tracing is explicitly enabled via environment variables."""
    val = (
        os.environ.get("ENABLE_CLOUD_TRACING")
        or os.environ.get("OTEL_TO_CLOUD")
        or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY")
        or ""
    ).strip().lower()
    return val in ("1", "true", "yes", "on")


def setup_cloud_tracing(
    enable_cloud_tracing: bool | None = None,
    service_name: str = "agent-guardian",
    project_id: str | None = None,
) -> bool:
    """
    Initializes OpenTelemetry providers and exports agent traces to Google Cloud Trace.

    Args:
        enable_cloud_tracing: Explicit flag. If None, checks `is_cloud_tracing_enabled()`.
        service_name: OpenTelemetry service name (default 'agent-guardian').
        project_id: GCP project ID for trace exporter. If None, reads GOOGLE_CLOUD_PROJECT.

    Returns:
        bool: True if Cloud Tracing was initialized, False otherwise.
    """
    if enable_cloud_tracing is None:
        enable_cloud_tracing = is_cloud_tracing_enabled()

    if not enable_cloud_tracing:
        logger.debug("Google Cloud Trace is disabled.")
        return False

    project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if not project:
        logger.warning(
            "ENABLE_CLOUD_TRACING is set, but GOOGLE_CLOUD_PROJECT is missing. "
            "Google Cloud Trace export will be skipped."
        )
        return False

    try:
        # Standard OpenTelemetry environment variables for semantic attributes
        os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
        os.environ.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES",
            f"service.name={service_name},service.version=0.1.0,cloud.provider=gcp,cloud.platform=cloud_run,gcp.project_id={project}",
        )
        # GenAI span content capture (opt-in to prevent 400 Bad Request from oversized prompt attributes)
        if os.environ.get("ENABLE_GENAI_SPAN_CONTENT", "").lower() in ("1", "true", "yes"):
            os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_agent_spans")

        from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
        from google.adk.telemetry.setup import maybe_set_otel_providers

        gcp_hooks = get_gcp_exporters(
            enable_cloud_tracing=True,
            enable_cloud_logging=False,
            enable_cloud_metrics=False,
        )
        otel_resource = get_gcp_resource(project_id=project)
        maybe_set_otel_providers(
            otel_hooks_to_setup=[gcp_hooks],
            otel_resource=otel_resource,
        )

        logger.info(
            "✓ Google Cloud Trace exporter initialized successfully for project '%s' (service='%s')",
            project,
            service_name,
        )
        return True

    except Exception as e:
        logger.warning("Failed to initialize Google Cloud Trace exporter: %s", e)
        return False
