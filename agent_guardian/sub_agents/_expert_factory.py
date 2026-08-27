from __future__ import annotations

"""
Factory for creating parallel expert review agents.

All review experts that use the GitHub + ingestion toolset share an identical
contract. This factory eliminates the boilerplate while preserving the flexibility
to inject expert-specific callbacks and extra tools.
"""

from typing import Any, Callable, List, Optional

from google.adk.agents import LlmAgent

from ..config import Config
from ..tools import (
    github_get_file_contents,
    github_get_multiple_files,
    github_get_recursive_tree,
    github_list_directory_contents,
    github_list_multiple_directories,
    parse_uploaded_files,
    read_artifact_file,
    pull_gcp_skill,
    list_available_gcp_skills,
)
from ..utils.mcp_factory import get_github_mcp_toolset
from ..utils.skill_loader import get_skill_toolset
from ..utils.tool_guards import block_github_misuse

_cfg = Config()

def get_base_tools() -> List[Any]:
    """Assemble the base toolset for review experts, resolving fresh toolsets."""
    tools: List[Any] = [
        parse_uploaded_files,
        read_artifact_file,
        pull_gcp_skill,
        list_available_gcp_skills,
        github_get_file_contents,
        github_list_directory_contents,
        github_get_multiple_files,
        github_list_multiple_directories,
        github_get_recursive_tree,
    ]
    github_mcp = get_github_mcp_toolset()
    if github_mcp is not None:
        tools.append(github_mcp)

    skill_ts = get_skill_toolset()
    if skill_ts is not None:
        tools.append(skill_ts)
    return tools


def make_expert_agent(
    *,
    name: str,
    model: str,
    description: str,
    instruction: str,
    output_key: str,
    extra_tools: Optional[List[Any]] = None,
    before_agent_callback: Optional[Callable] = None,
    after_agent_callback: Optional[Callable] = None,
) -> LlmAgent:
    """Build a parallel expert review LlmAgent with the standard tool contract.

    Args:
        name: ADK agent name (must be unique within the pipeline).
        model: Gemini model string.
        description: One-line capability description.
        instruction: Fully-rendered prompt string.
        output_key: State key where ADK persists the agent's output.
        extra_tools: Additional tools prepended before the base toolset.
            (e.g. governance uses scan_governance; adk_expert uses get_model_lifecycle)
        before_agent_callback: Optional pre-flight hook.
        after_agent_callback: Optional post-run hook.
    """
    base_tools = get_base_tools()
    tools = list(extra_tools or []) + base_tools

    kwargs: dict[str, Any] = dict(
        name=name,
        model=model,
        description=description,
        instruction=instruction,
        tools=tools,
        output_key=output_key,
        include_contents="none",
        before_tool_callback=block_github_misuse,
        generate_content_config=_cfg.safety_config,
    )
    if before_agent_callback is not None:
        kwargs["before_agent_callback"] = before_agent_callback
    if after_agent_callback is not None:
        kwargs["after_agent_callback"] = after_agent_callback

    return LlmAgent(**kwargs)
