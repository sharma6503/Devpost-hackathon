from __future__ import annotations

"""
Architecture & Framework Expert Agent.

Role in Pipeline:
Executes within the `parallel_review_experts` group during the Quality Gate Loop.
Specializes in Google ADK architecture patterns, API usage, and Gemini model lifecycle audits.
Uses `fetch_docs` to prevent hallucinations regarding the ADK framework.

State Interactions:
- Reads: `code_logic`, `code_config`, `confluence_rules`, `is_large_codebase`, `review_plan`, `module_map`
- Writes: `adk_review_result`
"""

import logging

from google.adk.agents.callback_context import CallbackContext

from ..config import Config
from ..prompts import ADK_EXPERT_PROMPT
from ..tools import get_model_lifecycle
from ..utils.compat import SafeMcpToolset
from ..utils.mcp_factory import get_adk_docs_toolset
from ._expert_factory import make_expert_agent

logger = logging.getLogger(__name__)
_cfg = Config()

# ADK-specific extra tools: model lifecycle + optional ADK docs MCP
_extra_tools = [get_model_lifecycle]

_adk_docs_mcp = get_adk_docs_toolset()
if _adk_docs_mcp is not None:
    _extra_tools.append(_adk_docs_mcp)


def adk_expert_callback(callback_context: CallbackContext):
    """Debug callback to verify expert output."""
    res = callback_context.state.get("adk_review_result", "")
    logger.info(f"ADK EXPERT CALLBACK: Output length: {len(res)}.")


async def adk_expert_preflight(callback_context: CallbackContext):
    """Pre-flight check to warn the agent if ADK Docs tools failed to load."""
    agent = callback_context.get_invocation_context().agent
    if agent is None or not hasattr(agent, "tools"):
        logger.warning("adk_expert_preflight: agent not yet available in context, skipping tool check")
        return

    mcp_toolsets = [t for t in agent.tools if isinstance(t, SafeMcpToolset)]

    docs_available = False
    for toolset in mcp_toolsets:
        conn_str = str(getattr(toolset, "connection_params", ""))
        if "adk.dev" in conn_str or "mcpdoc" in conn_str:
            if not getattr(toolset, "last_error", None):
                docs_available = True
                break

    if not docs_available:
        note = (
            "\n[SYSTEM NOTE: The 'fetch_docs' and 'list_doc_sources' tools are CURRENTLY UNAVAILABLE "
            "due to an environment restriction. DO NOT attempt to call them. Base your ADK "
            "review on your best internal knowledge, but DO NOT quote the docs verbatim as "
            "you cannot verify them live. Model Lifecycle Audit still works.]\n"
        )
        current_logic = callback_context.state.get("code_logic", "")
        callback_context.state["code_logic"] = note + current_logic


adk_expert = make_expert_agent(
    name="architecture_and_framework_expert",
    model=_cfg.agent_settings.adk_expert_model,
    description="Unified expert in Google ADK, Model Lifecycle, and General System Architecture.",
    instruction=ADK_EXPERT_PROMPT,
    output_key="adk_review_result",
    extra_tools=_extra_tools,
    before_agent_callback=adk_expert_preflight,
    after_agent_callback=adk_expert_callback,
)
