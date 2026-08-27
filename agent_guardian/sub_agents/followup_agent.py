from __future__ import annotations

"""
Follow-up Q&A Agent.

Role in Pipeline:
NOT part of the review pipeline. Registered as a second sub-agent on the root
supervisor. The supervisor transfers here when a review has already completed in
the session and the user asks a follow-up question about it (no new codebase
input). It answers from the saved review state and calls read-only investigative
tools only when fresh data is required — it never re-runs the audit pipeline and
never performs write/remediation actions.

State Interactions:
- Reads: `followup_question`, `synthesis_result`, `review_metrics`, all
  `*_review_result`, `validation_result`, `module_map`,
  `authorized_github_owner`, `authorized_github_repo`, `remediation_plan`,
  plus ingested `code_logic`/`code_config` (consumed by run_static_analysis).
- Writes: `followup_answer` (a persisted copy of the answer; the answer is also
  streamed to the user directly).
"""

import logging
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from ..config import Config
from ..prompts import FOLLOWUP_AGENT_PROMPT
from ..tools import (
    parse_uploaded_files,
    read_artifact_file,
    run_static_analysis,
    scan_governance,
    pull_gcp_skill,
    list_available_gcp_skills,
    get_model_lifecycle,
    github_get_file_contents,
    github_list_directory_contents,
    github_get_multiple_files,
    github_list_multiple_directories,
    github_get_recursive_tree,
)
from ..utils.mcp_factory import get_adk_docs_toolset, get_github_mcp_toolset
from ..utils.skill_loader import get_skill_toolset
from ..utils.tool_guards import block_github_misuse
from ..utils.resilience import safe_callback

logger = logging.getLogger(__name__)

_cfg = Config()


@safe_callback
async def _seed_followup_question(callback_context: CallbackContext) -> None:
    """Copy the latest user turn into state['followup_question'].

    Mirrors how constitution_callback captures the user request from
    `callback_context.user_content`. This makes the `{followup_question}`
    placeholder reliable instead of depending on the supervisor to emit a
    state write when it transfers here.
    """
    user_content = getattr(callback_context, "user_content", None)
    if not user_content or not getattr(user_content, "parts", None):
        return
    texts = [p.text for p in user_content.parts if getattr(p, "text", None)]
    if texts:
        callback_context.state["followup_question"] = "\n".join(texts).strip()


# ---------------------------------------------------------------------------
# Toolset: READ-ONLY investigative tools only.
# Deliberately EXCLUDES every write/remediation tool (github_create_branch,
# github_create_or_update_file, github_create_pull_request) — a follow-up must
# never mutate a repo.
# ---------------------------------------------------------------------------
_tools = [
    read_artifact_file,
    parse_uploaded_files,
    run_static_analysis,
    scan_governance,
    pull_gcp_skill,
    list_available_gcp_skills,
    get_model_lifecycle,
    github_get_file_contents,
    github_list_directory_contents,
    github_get_multiple_files,
    github_list_multiple_directories,
    github_get_recursive_tree,
]

_adk_docs_mcp = get_adk_docs_toolset()
if _adk_docs_mcp is not None:
    _tools.append(_adk_docs_mcp)

_github_mcp = get_github_mcp_toolset()
if _github_mcp is not None:
    _tools.append(_github_mcp)

_skill_toolset = get_skill_toolset()
if _skill_toolset is not None:
    _tools.append(_skill_toolset)

followup_agent = LlmAgent(
    name="followup_agent",
    model=_cfg.agent_settings.followup_model,
    description=(
        "Answers follow-up questions about a COMPLETED code review using the saved "
        "findings; fetches fresh data with read-only tools only when needed. Use this "
        "when a prior review exists in the session and the user asks a question about "
        "it (no new codebase, URL, file, or code snippet)."
    ),
    instruction=FOLLOWUP_AGENT_PROMPT,
    tools=_tools,
    output_key="followup_answer",  # persists a copy; the answer is also streamed to the user
    include_contents="default",  # conversational — needs the user's question turn(s)
    disallow_transfer_to_parent=True,  # prevents next-turn stickiness; supervisor re-routes each turn
    disallow_transfer_to_peers=True,  # a new review must go back through the supervisor
    before_agent_callback=_seed_followup_question,
    before_tool_callback=block_github_misuse,
    generate_content_config=_cfg.safety_config,
)
