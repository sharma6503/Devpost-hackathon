from __future__ import annotations

"""
Agent Guardian — Main Agent Orchestration (Modularized Assembly Entrypoint)
=============================================

This module acts as the clean, decoupled assembly point for the Agent Guardian
multi-agent system. It configures the final `root_agent` (supervisor), the main
`review_pipeline` (SequentialAgent), and the production-grade `app`.

Internal logic has been decoupled into:
- `agent_guardian/workflows/review.py` (review and remediation pipelines/workflows)
- `agent_guardian/utils/callbacks.py` (pipeline execution and zip callbacks)
- `agent_guardian/utils/bootstrap.py` (platform compatibility, naming patches, and hierarchy setup)
"""

import logging
from dotenv import load_dotenv

load_dotenv(override=True)

# 1. Initialize platform-level bootstrap hooks immediately before other imports
from agent_guardian.utils.bootstrap import bootstrap_platform, attach_parent_agents

bootstrap_platform()

from google.adk.apps.app import App, EventsCompactionConfig, ResumabilityConfig

from agent_guardian.utils.context_cache import get_cache_config as _get_cache_config
from agent_guardian.utils.token_utils import TokenSafetyPlugin

logger = logging.getLogger(__name__)

from google.adk.agents import LlmAgent
from agent_guardian.config import Config
from agent_guardian.prompts import SUPERVISOR_PROMPT

# Re-exports for backward compatibility and test-suite import safety
from agent_guardian.utils.callbacks import (
    constitution_callback,
    pacing_callback,
)
from agent_guardian.workflows.review import (
    WorkflowAgent,
    review_pipeline_agent,
    remediation_resume_agent,
)
from agent_guardian.sub_agents import followup_agent

__all__ = [
    "root_agent",
    "app",
    "constitution_callback",
    "pacing_callback",
    "WorkflowAgent",
]

configs = Config()

# Reset parent_agent and attachment flags on global singletons to prevent
# Pydantic validation errors during re-imports in test suites
for _singleton in [review_pipeline_agent, followup_agent, remediation_resume_agent]:
    if hasattr(_singleton, "parent_agent"):
        _singleton.parent_agent = None
    if hasattr(_singleton, "_parent_attached"):
        _singleton._parent_attached = False

from agent_guardian.utils.mcp_factory import get_adk_docs_toolset
from agent_guardian.utils.skill_loader import get_skill_toolset
from agent_guardian.tools.gcp_skill_tool import (
    pull_gcp_skill,
    list_available_gcp_skills,
    pull_multiple_gcp_skills,
)

_root_tools = [pull_gcp_skill, list_available_gcp_skills, pull_multiple_gcp_skills]
_adk_docs_mcp = get_adk_docs_toolset()
if _adk_docs_mcp is not None:
    _root_tools.append(_adk_docs_mcp)

_skill_toolset = get_skill_toolset()
if _skill_toolset is not None:
    _root_tools.append(_skill_toolset)

# Standalone root agent definition
root_agent = LlmAgent(
    name="root_agent",
    model=configs.agent_settings.root_model,
    description="Agent Guardian — Multi-Agent Audit Orchestrator.",
    before_agent_callback=constitution_callback,
    instruction=SUPERVISOR_PROMPT,
    sub_agents=[review_pipeline_agent, followup_agent, remediation_resume_agent],
    tools=_root_tools,
    generate_content_config=configs.safety_config,
)

# Connect parent_agent relationships across the entire graph
attach_parent_agents(root_agent)

from agent_guardian.utils.resilience import (
    GlobalResiliencePlugin,
    ErrorAwareReflectAndRetryToolPlugin,
)

app = App(
    name="agent_guardian",
    root_agent=root_agent,
    plugins=[
        ErrorAwareReflectAndRetryToolPlugin(
            max_retries=configs.max_retries,
            throw_exception_if_retry_exceeded=False,
        ),
        TokenSafetyPlugin(),
        GlobalResiliencePlugin(),
    ],
    context_cache_config=_get_cache_config(),
    events_compaction_config=EventsCompactionConfig(
        token_threshold=120000,
        event_retention_size=4,
        compaction_interval=10,
        overlap_size=2,
    ),
    resumability_config=ResumabilityConfig(is_resumable=True),
)
