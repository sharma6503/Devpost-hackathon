from __future__ import annotations

"""
Bootstrap and platform-level setup hooks for Agent Guardian.

Includes platform compatibility (setup_platform_compat), logging filters,
and agent hierarchy parent-linking.
"""

import logging
import os
from typing import Any
from google.adk.agents import BaseAgent

# 1. Setup platform compatibility IMMEDIATELY
from agent_guardian.utils.compat import setup_platform_compat

logger = logging.getLogger(__name__)


def bootstrap_platform() -> None:
    """Initialize platform compatibility and logging filters."""
    setup_platform_compat()

    # Configure Logging Filters
    class _McpTimeoutFilter(logging.Filter):
        """Demotes noisy MCP-session timeout ERRORs and BrokenResourceErrors to DEBUG."""

        _SUPPRESS = (
            "Exception during MCP session execution",
            "Failed to get tools from MCP server",
            "BrokenResourceError",
            "TaskGroup",
            "ExceptionGroup",
        )
        _AUTH_KEYWORDS = ("401", "403", "Unauthorized", "Forbidden", "auth", "credential")

        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            # Never suppress authentication / authorisation errors — these must reach Cloud Run logs
            if any(k in msg for k in self._AUTH_KEYWORDS):
                return True
            if record.levelno >= logging.ERROR and any(s in msg for s in self._SUPPRESS):
                record.levelno = logging.DEBUG
                record.levelname = "DEBUG"
            return True

    for _n in ["google.adk", "google_adk", "mcp", "anyio"]:
        logging.getLogger(_n).addFilter(_McpTimeoutFilter())

    # Clear process-level GOOGLE_API_KEY if Enterprise / Vertex AI is active to prevent auth collisions
    use_enterprise = os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("1", "true", "yes") or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
    if use_enterprise:
        os.environ.pop("GOOGLE_API_KEY", None)


def attach_parent_agents(agent: Any) -> None:
    """Recursively traverses the agent hierarchy and sets parent_agent on workflow nodes and inner resilient agents."""
    if agent is None:
        return
    if hasattr(agent, "_parent_attached") and agent._parent_attached:
        return
    agent._parent_attached = True

    # 1. If it's a ResilientAgent, set inner_agent's parent to the ResilientAgent itself,
    # and traverse the inner_agent.
    if hasattr(agent, "inner_agent") and agent.inner_agent is not None:
        if isinstance(agent.inner_agent, BaseAgent):
            agent.inner_agent.parent_agent = agent
        attach_parent_agents(agent.inner_agent)

    # 2. Extract workflow (for WorkflowAgent or raw Workflow)
    workflow = getattr(agent, "workflow", None)
    if workflow is None and (hasattr(agent, "edges") or agent.__class__.__name__ == "Workflow"):
        workflow = agent

    if workflow is not None:
        nodes = []
        edges = getattr(workflow, "edges", [])
        for edge in edges:
            if not isinstance(edge, tuple) or len(edge) != 2:
                continue
            u, v = edge
            for x in (u, v):
                if isinstance(x, (list, tuple, set)):
                    for item in x:
                        if item not in nodes:
                            nodes.append(item)
                elif isinstance(x, dict):
                    for item in x.values():
                        if item not in nodes:
                            nodes.append(item)
                else:
                    if x not in nodes:
                        nodes.append(x)
        for child_node in nodes:
            if isinstance(child_node, BaseAgent):
                child_node.parent_agent = agent
                attach_parent_agents(child_node)
            elif hasattr(child_node, "edges") or child_node.__class__.__name__ == "Workflow":
                attach_parent_agents(child_node)

    # 3. Traverse any direct sub_agents
    sub_agents = getattr(agent, "sub_agents", None)
    if sub_agents and isinstance(sub_agents, list):
        for sub_agent in sub_agents:
            attach_parent_agents(sub_agent)
