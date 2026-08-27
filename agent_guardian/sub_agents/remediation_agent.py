from __future__ import annotations

"""
agent_guardian/sub_agents/remediation_agent.py

GitHub MCP Remediation Agent — Automated PR Generation.

Role in Pipeline:
Runs as the final step in the `review_pipeline` (optional/conditional).
It consumes the synthesized markdown report and extracts actionable, mechanical fixes.
It then creates a new git branch, commits the changes, and opens a Pull Request on GitHub.

State Interactions:
- Reads: `synthesis_result`, `user_request`
- Writes: `remediation_plan` (JSON), `remediation_pr_url`, `remediation_skipped`

Architecture (2-stage):
  ┌─────────────────────────────────────────────────────────────┐
  │  remediation_planner     (LlmAgent — output_schema)         │
  │    Reads synthesis_result → produces RemediationPlan JSON   │
  │    written to state['remediation_plan']                     │
  └───────────────────────────┬─────────────────────────────────┘
                              │ Workflow
  ┌───────────────────────────▼─────────────────────────────────┐
  │  remediation_executor    (LlmAgent — GitHub MCP tools)      │
  │    Reads remediation_plan → creates branch, commits files,  │
  │    opens PR via GitHub MCP API                              │
  │    writes pr_url to state['remediation_pr_url']             │
  └─────────────────────────────────────────────────────────────┘

Why 2-stage?
  output_schema disables tool calls (ADK limitation). We use a dedicated
  planner agent (schema only, no tools) to produce the structured plan,
  then hand off to the executor agent (tools only, no schema) to execute it.

GitHub MCP Toolset used:
  - create_branch           — creates 'guardian/remediation-YYYY-MM-DD'
  - create_or_update_file   — commits each changed file to the branch
  - create_pull_request     — opens the PR with full description

Environment Variables:
  GITHUB_TOKEN               — PAT with repo + PR write permissions
  GITHUB_REMEDIATION_REPO    — default target repo ('owner/repo')
  GITHUB_BASE_BRANCH         — default base branch (default: 'main')
  REMEDIATION_AUTO_PR        — set to 'false' to skip PR creation (dry-run)
"""

import os
import re
import json
import logging
from datetime import datetime, timezone

from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow, START, FunctionNode
from google.adk import Event
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types as _genai_types

from agent_guardian.config import Config, _env_int
from agent_guardian.models import RemediationPlan
from agent_guardian.prompts import (
    REMEDIATION_RESEARCH_PROMPT,
    REMEDIATION_PLANNER_PROMPT,
    REMEDIATION_EXECUTOR_PROMPT,
)
from agent_guardian.tools import (
    github_get_file_contents,
    github_list_directory_contents,
    github_get_multiple_files,
    github_list_multiple_directories,
    github_get_recursive_tree,
    github_create_branch,
    github_create_or_update_file,
    github_create_pull_request,
    github_apply_remediation_plan,
    bitbucket_apply_remediation_plan,
    apply_remediation_plan,
    github_fetch_file_raw,
    get_file_contents,
    create_branch,
    create_or_update_file,
    create_pull_request,
    get_model_lifecycle,
)
from ..utils.compat import SafeMcpToolset
from ..utils.mcp_factory import get_adk_docs_toolset, get_github_write_mcp_toolset
from ..utils.resilience import resilient
from ..utils.tool_guards import block_github_misuse

logger = logging.getLogger(__name__)
_cfg = Config()

# ---------------------------------------------------------------------------
# GitHub tools — combine MCP and REST fallbacks (dynamically isolated to avoid name collision)
# ---------------------------------------------------------------------------
_gh_tools = [
    github_get_file_contents,
    github_list_directory_contents,
    github_get_multiple_files,
    github_list_multiple_directories,
    github_get_recursive_tree,
    github_create_branch,
    github_create_or_update_file,
    github_create_pull_request,
]

_auto_pr = os.environ.get("REMEDIATION_AUTO_PR", "true").lower() != "false"

# Shared read/write GitHub MCP toolset built once in mcp_factory (repo/files/
# pull_requests/git scope). None when GITHUB_TOKEN / npx are unavailable — in that
# case fall back to the REST tools, kept separate to avoid duplicate tool-name
# collisions with the MCP server.
_github_mcp = get_github_write_mcp_toolset()
if _github_mcp is not None:
    _gh_tools.append(_github_mcp)
    logger.info("remediation_agent: shared GitHub write MCP toolset loaded.")
else:
    logger.info("remediation_agent: GitHub MCP unavailable. Using REST fallbacks only.")
    _gh_tools.extend(
        [
            get_file_contents,
            create_branch,
            create_or_update_file,
            create_pull_request,
        ]
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


# Repo-relative code paths cited in findings, e.g. `agent_guardian/agent.py`.
# Requires at least one "/" so we only fetch locatable paths, not bare filenames.
_SRC_PATH_RE = re.compile(
    r"([A-Za-z0-9_][\w.\-]*(?:/[\w.\-]+)+\.(?:py|pyi|tsx|ts|jsx|js|mjs|cjs|json|ya?ml"
    r"|toml|ini|cfg|txt|md|html|css|scss|sh|go|java|rb|rs|cpp|cc|hpp|c|h|sql|env|dockerfile))"
    r"(?![A-Za-z0-9])"
)
_MAX_SOURCE_FILES = _env_int("REMEDIATION_MAX_SOURCE_FILES", 25)
_MAX_SOURCE_FILE_BYTES = _env_int("REMEDIATION_MAX_SOURCE_FILE_BYTES", 30000)
_MAX_SOURCE_TOTAL_BYTES = _env_int("REMEDIATION_MAX_SOURCE_TOTAL_BYTES", 250000)


async def _planner_before_callback(callback_context: CallbackContext):
    """Fetch the RAW source of files cited in the findings and inject it into the
    planner prompt as ``state['remediation_source_context']``.

    Root fix for partial/empty remediation PRs: the planner uses output_schema
    (no tools) so it can't read code, and was inventing ``original_snippet``s that
    never matched the repo verbatim — so every 'modify' failed the apply step's
    exact-match check and only 'create's landed. Feeding it the real source (the
    SAME bytes the apply step matches against) lets it copy snippets verbatim.

    Mirrors ``_research_preflight``: mutates state the planner's own instruction
    template injects. Best-effort — never raises (a fetch flake must not abort the
    remediation flow); on any failure it writes a fallback note.
    """
    state = callback_context.state
    fallback = (
        "(No repository source could be fetched. Base fixes on the synthesis "
        "report; prefer change_type='create' and do NOT invent original_snippet.)"
    )
    try:
        synthesis = str(state.get("synthesis_result") or "")
        owner = str(state.get("authorized_github_owner") or "").strip()
        repo = str(state.get("authorized_github_repo") or "").strip()
        cfg = Config()
        # Fetch from the SAME repo the apply step will push to / match against:
        # configured remediation repo, else the reviewed repo.
        target = (cfg.github_remediation_repo or "").strip() or (f"{owner}/{repo}" if owner and repo else "")
        if not synthesis or "/" not in target:
            state["remediation_source_context"] = fallback
            return
        t_owner, _, t_repo = target.partition("/")
        t_owner, t_repo = t_owner.strip(), t_repo.strip()
        base = state.get("authorized_github_ref") or cfg.github_base_branch or "main"

        # Candidate paths cited in the findings, in order, de-duplicated.
        seen: list[str] = []
        for m in _SRC_PATH_RE.finditer(synthesis):
            p = m.group(1).lstrip("./")
            if "github.com" in p or p.startswith("http") or "://" in p:
                continue
            if p not in seen:
                seen.append(p)
            if len(seen) >= _MAX_SOURCE_FILES:
                break
        if not seen:
            state["remediation_source_context"] = fallback
            return

        # Fetch all cited files concurrently — this was a serial await loop (up to
        # _MAX_SOURCE_FILES round-trips back-to-back on the planner's critical path).
        # Order is preserved via zip(seen, ...) so the byte-budget trimming below
        # stays deterministic. return_exceptions keeps the "never raises" contract:
        # a fetch flake becomes a skipped file, not an abort.
        import asyncio

        results = await asyncio.gather(
            *(github_fetch_file_raw(t_owner, t_repo, p, base) for p in seen),
            return_exceptions=True,
        )
        blocks: list[str] = []
        total = 0
        for path, res in zip(seen, results):
            if not isinstance(res, dict) or res.get("status") != "ok" or not res.get("content"):
                continue
            content = res["content"]
            note = ""
            if len(content) > _MAX_SOURCE_FILE_BYTES:
                content = content[:_MAX_SOURCE_FILE_BYTES]
                note = (
                    "\n# [TRUNCATED — only copy original_snippet from the portion "
                    "shown above; for code below this point use change_type='create' or skip]"
                )
            block = f"--- {path} ---\n{content}{note}"
            if total + len(block) > _MAX_SOURCE_TOTAL_BYTES:
                break
            blocks.append(block)
            total += len(block)

        state["remediation_source_context"] = "\n\n".join(blocks) if blocks else fallback
        logger.info(
            "remediation_planner: prefetched %d/%d source file(s) from %s for verbatim snippets (%d bytes).",
            len(blocks),
            len(seen),
            target,
            total,
        )
    except Exception as e:
        logger.warning("remediation_planner: source prefetch failed — %s", e)
        state["remediation_source_context"] = fallback


def _planner_after_callback(callback_context: CallbackContext):
    """
    Validates and enriches the RemediationPlan produced by the planner.
    - Parses JSON, validates against RemediationPlan schema.
    - Injects GITHUB_REMEDIATION_REPO and date-stamped branch name if missing.
    - Writes canonical JSON back to state so executor reads a clean plan.
    """
    if callback_context.state.get("remediation_skipped"):
        return

    raw = callback_context.state.get("remediation_plan", "")
    if not raw:
        logger.warning("remediation_planner: no output in state['remediation_plan'].")
        return

    if isinstance(raw, dict):
        data = raw
    elif hasattr(raw, "model_dump"):
        data = raw.model_dump()
    else:
        # Fallback for string parsing
        import re

        cleaned = str(raw).strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"remediation_planner: JSON parse failed — {e}. Raw: {raw[:300]}")
            return
    # Using fresh Config() to respect dynamic environment changes during tests
    current_config = Config()

    # Inject defaults from environment or reviewed repo if agent left them blank.
    # Precedence: plan LLM output → env GITHUB_REMEDIATION_REPO → reviewed repo from state.
    if not data.get("target_repo"):
        if current_config.github_remediation_repo:
            data["target_repo"] = current_config.github_remediation_repo
        else:
            _owner = str(callback_context.state.get("authorized_github_owner") or "").strip()
            _repo = str(callback_context.state.get("authorized_github_repo") or "").strip()
            if _owner and _repo:
                data["target_repo"] = f"{_owner}/{_repo}"
                logger.info("remediation_planner: target_repo inferred from reviewed repo → %s/%s", _owner, _repo)
    if not data.get("pr_branch"):
        data["pr_branch"] = "agent_guardian/review"
    if not data.get("base_branch"):
        data["base_branch"] = callback_context.state.get("authorized_github_ref") or current_config.github_base_branch

    try:
        plan = RemediationPlan(**data)
        callback_context.state["remediation_plan"] = plan.model_dump_json(indent=2)
        logger.info(
            f"remediation_planner: plan validated — {len(plan.changes)} change(s), "
            f"priority={plan.priority}, risk={plan.estimated_risk}, "
            f"repo={plan.target_repo}, branch={plan.pr_branch}"
        )
        from ..utils.markdown_format import format_remediation_plan_md

        md_text = format_remediation_plan_md(plan)
        callback_context.state["remediation_plan_md"] = md_text
        return None
    except Exception as e:
        logger.error(f"remediation_planner: RemediationPlan validation failed — {e}")


# Statuses set by the before-callback that mean "the executor LLM did NOT run and
# produced no PR" — the after-callback must leave them (and the empty URL) intact.
_TERMINAL_BEFORE_STATUSES = {"skipped", "dry_run", "no_target", "pending_approval", "pending_commit_id"}

# Matches the first http(s) URL in free text; trailing punctuation is stripped.
_PR_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


def _set_terminal(callback_context: CallbackContext, *, status: str, message: str):
    """Finalize the remediation stage without a PR. Keeps remediation_pr_url EMPTY
    (it holds an http(s) URL only) and records the reason in remediation_status."""
    callback_context.state["remediation_status"] = status
    callback_context.state["remediation_pr_url"] = ""
    callback_context.state["remediation_pending_approval"] = status == "pending_approval"
    from google.genai import types

    return types.Content(role="model", parts=[types.Part.from_text(text=message)])


def _executor_before_callback(callback_context: CallbackContext):
    """
    Abort executor if dry-run mode is enabled, if MCP is unavailable,
    or if no target repository is defined. Also enforces the Human-in-the-Loop (HITL)
    remediation approval gate.

    Status/flags are written to dedicated state keys (remediation_status,
    remediation_skipped, remediation_pending_approval) — NEVER into
    remediation_pr_url, which is reserved for a real PR URL so the UI can't render
    a status message as a (broken) link.
    """
    # 1. Enforce Human-in-the-Loop (HITL) approval gate
    remediation_approved = callback_context.state.get("remediation_approved", False)
    remediation_skipped = callback_context.state.get("remediation_skipped", False)

    if remediation_skipped:
        logger.info("remediation_executor: Remediation skipped by user.")
        return _set_terminal(callback_context, status="skipped", message="Remediation skipped by user.")

    if not remediation_approved:
        logger.info("remediation_executor: Pausing execution, waiting for user approval.")

        # Build remediation summary from plan (shown to the user before approval).
        remediation_plan_raw = callback_context.state.get("remediation_plan", "")
        plan_data = None
        if isinstance(remediation_plan_raw, str) and remediation_plan_raw:
            try:
                plan_data = json.loads(remediation_plan_raw)
            except Exception:
                pass
        elif isinstance(remediation_plan_raw, dict):
            plan_data = remediation_plan_raw

        summary_parts = []
        if plan_data:
            summary_parts.append(f"### Proposed Pull Request: **{plan_data.get('pr_title', 'Remediation Review')}**")
            summary_parts.append(f"Target Repo: `{plan_data.get('target_repo', 'unknown')}`")
            summary_parts.append(f"Branch: `{plan_data.get('pr_branch', 'unknown')}`")
            summary_parts.append("\n**Proposed Changes:**")
            for change in plan_data.get("changes", []):
                summary_parts.append(
                    f"- **{change.get('change_type', 'modify').upper()}** `{change.get('file_path')}`: {change.get('rationale')}"
                )
        else:
            summary_parts.append("No proposed changes in remediation plan.")

        callback_context.state["remediation_plan_summary"] = "\n".join(summary_parts)
        return _set_terminal(
            callback_context,
            status="pending_approval",
            message="Remediation execution is pending user approval. Please approve or skip the proposed PR on the UI.",
        )

    # If approved, reset the pending flag and proceed
    logger.info("remediation_executor: Remediation approved by user. Checking for commit ID.")
    callback_context.state["remediation_pending_approval"] = False

    # Check if we need to request a Commit ID before committing
    remediation_commit_id = callback_context.state.get("remediation_commit_id")
    if not remediation_commit_id:
        logger.info("remediation_executor: Pausing execution, waiting for commit ID.")
        return _set_terminal(
            callback_context,
            status="pending_commit_id",
            message=(
                "### 🛡️ Remediation Approved!\n\n"
                "To proceed with creating the branch and committing the changes, "
                "**please provide a Commit ID or Jira Issue Key** (e.g., `EA-1234`).\n\n"
                "Your organization's repository requires a valid Commit ID in commit messages to satisfy "
                "pre-receive hooks.\n\n"
                "👉 Please type your **Commit ID / Issue Key** (or type `none` to proceed without one) in the chat."
            ),
        )

    # 2. Dry run checks
    if not _auto_pr:
        logger.info("remediation_executor: REMEDIATION_AUTO_PR=false — dry-run mode, skipping PR creation.")
        callback_context.state["remediation_skipped"] = True
        return _set_terminal(
            callback_context,
            status="dry_run",
            message="Remediation execution skipped (DRY_RUN).",
        )

    # 3. Resolve the push target. On an approval resume, user_request is the
    # approval sentinel (not the original repo URL), so we must NOT re-derive the
    # target from it. Precedence:
    #   (a) the plan's target_repo (env default already injected by the planner),
    #   (b) the configured GITHUB_REMEDIATION_REPO,
    #   (c) the reviewed repo (authorized_github_owner/repo), preserved in state
    #       across the approve turn because the sentinel isn't a GitHub URL.
    current_config = Config()

    plan = {}
    plan_raw = callback_context.state.get("remediation_plan", "")
    if hasattr(plan_raw, "model_dump") and callable(plan_raw.model_dump):
        plan = plan_raw.model_dump()
    elif hasattr(plan_raw, "dict") and callable(plan_raw.dict):
        plan = plan_raw.dict()
    elif isinstance(plan_raw, str) and plan_raw.strip():
        try:
            plan = json.loads(plan_raw) or {}
        except Exception:
            plan = {}
    elif isinstance(plan_raw, dict):
        plan = dict(plan_raw)

    plan_target = str(plan.get("target_repo") or "").strip()
    if plan_target.lower() in ("owner/repo", "workspace/repo"):  # bare placeholder is not a real target
        plan_target = ""

    owner = str(callback_context.state.get("authorized_github_owner") or "").strip()
    repo = str(callback_context.state.get("authorized_github_repo") or "").strip()
    reviewed_repo = f"{owner}/{repo}" if owner and repo else ""

    if not reviewed_repo:
        repo_name = str(callback_context.state.get("repo_name") or "").strip()
        if "/" in repo_name and repo_name.lower() not in ("owner/repo", "workspace/repo"):
            reviewed_repo = repo_name

    effective_target = plan_target or (current_config.github_remediation_repo or "") or reviewed_repo

    if not effective_target:
        logger.info("remediation_executor: No target repository defined. Skipping PR creation.")
        callback_context.state["remediation_skipped"] = True
        return _set_terminal(
            callback_context,
            status="no_target",
            message="Remediation execution skipped (No target repository defined).",
        )

    # Ensure the executor pushes to the resolved target — the plan may carry a
    # placeholder (or nothing) when no default repo is configured.
    if plan and plan_target != effective_target:
        plan["target_repo"] = effective_target
        callback_context.state["remediation_plan"] = json.dumps(plan)
        logger.info("remediation_executor: target_repo resolved to %s", effective_target)


def _executor_after_callback(callback_context: CallbackContext):
    """Distill the executor's raw output into a clean PR URL + status.

    The executor writes its free-text response to state['remediation_executor_raw']
    (its output_key). Here we extract the actual PR URL from it and publish it to
    remediation_pr_url, setting remediation_status accordingly. This guarantees
    remediation_pr_url is either empty or a navigable http(s) URL — never prose.
    """
    state = callback_context.state

    if state.get("temp:apply_remediation_looped"):
        logger.warning(
            "remediation_executor: loop detected — LLM called github_apply_remediation_plan "
            "more than once. Recovering from tool-call result already in state."
        )
        state.pop("temp:apply_remediation_looped", None)

    # A before-callback branch already finalized the stage (no PR produced).
    if state.get("remediation_status") in _TERMINAL_BEFORE_STATUSES:
        logger.info(
            "remediation_executor: status=%s (no PR created).",
            state.get("remediation_status"),
        )
        return

    # PRIMARY: read the deterministic apply tool's structured response straight
    # from the session events. This is authoritative — committed/failed/pr_url all
    # come from Python, not from parsing the LLM's prose.
    tool_result = _extract_apply_result(callback_context)
    if tool_result is not None:
        pr_url = str(tool_result.get("pr_url", "") or "")
        failed = tool_result.get("failed", []) or []
        committed = tool_result.get("committed", []) or []
        state["remediation_failed_changes"] = failed
        if pr_url:
            state["remediation_pr_url"] = pr_url
            # "partial" when a PR opened but some changes failed exact-match/commit.
            state["remediation_status"] = "partial" if failed else "created"
            logger.info(
                "remediation_executor: PR %s — %d committed, %d failed.",
                pr_url,
                len(committed),
                len(failed),
            )
        else:
            state["remediation_pr_url"] = ""
            state["remediation_status"] = "failed"
            logger.warning(
                "remediation_executor: apply produced no PR — %s (failed=%d)",
                tool_result.get("message", "no message"),
                len(failed),
            )
        return

    # FALLBACK: no structured result found (e.g. LLM answered without calling the
    # tool) — recover a URL from the raw text if one is present.
    raw = state.get("remediation_executor_raw", "") or ""
    match = _PR_URL_RE.search(str(raw))
    if match:
        url = match.group(0).rstrip(".,);]")
        state["remediation_pr_url"] = url
        state["remediation_status"] = "created"
        logger.info(f"remediation_executor: PR created — {url}")
    else:
        state["remediation_pr_url"] = ""
        state["remediation_status"] = "failed"
        logger.warning(
            "remediation_executor: no PR URL found in executor output — %s",
            str(raw)[:200],
        )


def _extract_apply_result(callback_context: CallbackContext) -> dict | None:
    """Find the most recent apply_remediation_plan / github_apply_remediation_plan tool response in events."""
    result = None
    session = getattr(callback_context, "session", None)
    events = getattr(session, "events", None) if session else None
    if not events:
        return None
    for event in events:
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            fn_resp = getattr(part, "function_response", None)
            if not fn_resp or getattr(fn_resp, "name", "") not in (
                "github_apply_remediation_plan",
                "bitbucket_apply_remediation_plan",
                "apply_remediation_plan",
            ):
                continue
            resp = fn_resp.response
            if resp is not None and not isinstance(resp, dict):
                if hasattr(resp, "model_dump") and callable(resp.model_dump):
                    resp = resp.model_dump()
                elif hasattr(resp, "to_dict") and callable(resp.to_dict):
                    resp = resp.to_dict()
                elif hasattr(resp, "dict") and callable(resp.dict):
                    resp = resp.dict()
            if isinstance(resp, dict):
                # Unwrap ADK / GenAI standard function response wrappers {"result": {...}}
                if "result" in resp and isinstance(resp["result"], dict):
                    resp = resp["result"]
                elif "output" in resp and isinstance(resp["output"], dict):
                    resp = resp["output"]

                # Skip guard-blocked responses — the guard returns
                # {"status": "terminal", "error": "APPLY_ALREADY_RAN"} as a
                # FunctionResponse when it blocks a repeat call, which also lands
                # in session.events. Keeping the last match would overwrite the
                # real tool result with the guard's error dict (no pr_url → "failed").
                if resp.get("error") == "APPLY_ALREADY_RAN":
                    continue
                result = resp  # keep the last real result
    return result


# ---------------------------------------------------------------------------
# Stage 0: Researcher — consults ADK docs MCP BEFORE any code is written.
#
# The planner (Stage 1) uses output_schema, which disables tool calls, so it
# cannot look anything up itself. This stage runs first, calls the ADK-docs MCP
# (fetch_docs / list_doc_sources) + model-lifecycle tool to verify the APIs and
# model ids involved in the fixes, and writes grounded notes to
# state['adk_remediation_context'], which the planner injects. This enforces
# "consult the docs, THEN generate code" structurally via the workflow order.
# ---------------------------------------------------------------------------
_research_tools = [get_model_lifecycle]
_adk_docs_mcp = get_adk_docs_toolset()
if _adk_docs_mcp is not None:
    _research_tools.append(_adk_docs_mcp)
    logger.info("remediation_agent: ADK-docs MCP toolset loaded for remediation_research.")
else:
    logger.info("remediation_agent: ADK-docs MCP unavailable — research falls back to internal knowledge.")


async def _research_preflight(callback_context: CallbackContext):
    """Warn the researcher (via a SYSTEM NOTE) if the ADK-docs tools failed to load,
    mirroring adk_expert_preflight — so it doesn't try to call missing tools."""
    try:
        agent = callback_context.get_invocation_context().agent
        if agent is None or not hasattr(agent, "tools"):
            return
        toolsets = [t for t in agent.tools if isinstance(t, SafeMcpToolset)]
        docs_ok = any(
            "adk.dev" in str(getattr(t, "connection_params", "")) and not getattr(t, "last_error", None)
            for t in toolsets
        )
        if not docs_ok:
            note = (
                "\n[SYSTEM NOTE: The 'fetch_docs' and 'list_doc_sources' tools are CURRENTLY "
                "UNAVAILABLE. DO NOT attempt to call them. Base your notes on best internal "
                "knowledge WITHOUT claiming doc verification. get_model_lifecycle still works.]\n"
            )
            callback_context.state["synthesis_result"] = note + str(callback_context.state.get("synthesis_result", ""))
    except Exception as e:
        logger.debug(f"_research_preflight skipped: {e}")


remediation_research = LlmAgent(
    model=_cfg.agent_settings.remediation_model,
    name="remediation_research",
    description=(
        "Consults the ADK/Gemini documentation (fetch_docs MCP) and model-lifecycle "
        "tool to verify APIs and model ids BEFORE the planner writes remediation code."
    ),
    instruction=REMEDIATION_RESEARCH_PROMPT,
    output_key="adk_remediation_context",
    include_contents="none",  # all context from state injection ({synthesis_result})
    generate_content_config=_cfg.generation_config(_cfg.agent_settings.remediation_temperature),
    before_agent_callback=_research_preflight,
    before_tool_callback=block_github_misuse,
)

# Resilient wrapper: a docs-MCP flake must not abort the whole remediation flow.
# On terminal failure it writes the fallback note to adk_remediation_context so
# the planner still proceeds (from internal knowledge).
remediation_research_r = resilient(
    remediation_research,
    fallback_text="[ADK docs lookup unavailable — plan from internal knowledge, do not claim doc verification.]",
)


# ---------------------------------------------------------------------------
# Stage 1: Planner — structured output, no tools
# ---------------------------------------------------------------------------
_today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# The planner emits a RemediationPlan that embeds full replacement_snippet code
# blocks for every changed file, so it needs far more headroom than the global
# 8192 ceiling. A truncated response is fatal here: ADK validates output_schema
# in __maybe_save_output_to_state (before our after-callback runs), so a cut-off
# JSON string raises a ValidationError that fails the whole root node — it cannot
# be recovered downstream. Mirrors the html_agent override.
_planner_config = _cfg.generation_config(_cfg.agent_settings.remediation_temperature)
_planner_config.max_output_tokens = _env_int("REMEDIATION_MAX_OUTPUT_TOKENS", 32768)

remediation_planner = LlmAgent(
    model=_cfg.agent_settings.remediation_model,
    name="remediation_planner",
    description=(
        "Reads the synthesis report and produces a structured RemediationPlan: "
        "which files to change, what to change, and what PR metadata to create."
    ),
    instruction=REMEDIATION_PLANNER_PROMPT.replace("{today}", _today_str)
    .replace("{default_repo}", _cfg.github_remediation_repo or "owner/repo")
    .replace("{base_branch}", _cfg.github_base_branch),
    output_key="remediation_plan",
    output_schema=RemediationPlan,  # Forces structured JSON — no tool calls
    include_contents="none",  # All context from state injection
    generate_content_config=_planner_config,
    before_agent_callback=_planner_before_callback,
    after_agent_callback=_planner_after_callback,
)


# ---------------------------------------------------------------------------
# Stage 2: Executor — GitHub tools, reads plan from state, no schema
# ---------------------------------------------------------------------------


# ADK-native loop-breaker: after github_apply_remediation_plan runs once,
# before_tool_callback sets temp:apply_remediation_called. When ADK calls the
# LLM a second time to get a final text response, this callback intercepts it
# and returns a canned LlmResponse, preventing the LLM from generating another
# function call and spinning into an infinite tool-call loop.
def _summarize_apply(callback_context: CallbackContext) -> str:
    """Build a human-facing remediation summary (PR link + committed/failed) from
    the deterministic apply tool's structured result — so the chat concludes with
    a real outcome instead of an opaque 'recorded in session state' line."""
    res = _extract_apply_result(callback_context) or {}
    pr_url = str(res.get("pr_url") or "")
    committed = res.get("committed") or []
    failed = res.get("failed") or []
    if pr_url:
        lines = [f"✅ **Remediation PR opened:** {pr_url}", ""]
        summary = f"- **{len(committed)}** change(s) committed"
        if failed:
            summary += f", **{len(failed)}** could not be applied"
        lines.append(summary)
        if failed:
            lines.append("\n**Not applied** (exact-match failed — review manually):")
            for f in failed[:10]:
                lines.append(
                    f"- `{f.get('file_path', '?')}` ({f.get('finding_id', '?')}): {f.get('reason', 'unknown')}"
                )
            if len(failed) > 10:
                lines.append(f"- …and {len(failed) - 10} more")
        lines.append("\nReview the PR before merging.")
        return "\n".join(lines)
    msg = str(res.get("message") or res.get("error") or "no PR was created")
    lines = [f"❌ **Remediation did not open a PR** — {msg}."]
    if failed:
        lines.append("\n**Failed changes**:")
        for f in failed[:10]:
            lines.append(
                f"- `{f.get('file_path', '?')}` ({f.get('finding_id', '?')}): {f.get('reason', 'unknown')}"
            )
        if len(failed) > 10:
            lines.append(f"- …and {len(failed) - 10} more")
    return "\n".join(lines)


def _executor_before_model_callback(
    callback_context: CallbackContext,
    llm_request=None,
) -> LlmResponse | None:
    if callback_context.state.get("temp:apply_remediation_called"):
        logger.info(
            "remediation_executor: apply tool already ran — skipping second LLM call "
            "to prevent multi-turn tool-call loop."
        )
        return LlmResponse(
            content=_genai_types.Content(
                role="model",
                parts=[_genai_types.Part(text=_summarize_apply(callback_context))],
            )
        )
    return None


def _make_executor(name: str) -> LlmAgent:
    """Build a remediation-executor agent.

    A factory (rather than a shared singleton) because the executor runs in TWO
    graphs — the in-pipeline remediation flow and the standalone approval-resume
    flow — and an ADK agent can only have one parent. Each graph gets its own
    instance; they share the same prompt, tools, and callbacks.
    """
    return LlmAgent(
        model=_cfg.agent_settings.remediation_model,
        name=name,
        description=(
            "Executes the RemediationPlan: creates a Git branch, commits changed files, "
            "and opens a GitHub or Bitbucket PR via the provider APIs."
        ),
        instruction=REMEDIATION_EXECUTOR_PROMPT,
        # Scratch output_key: the after-callback distills this raw text into the clean
        # remediation_pr_url / remediation_status. Keeps prose out of the URL field.
        output_key="remediation_executor_raw",
        # Deterministic single-tool path: the apply tool creates the branch, merges
        # every change with exact-match verification, and opens the PR in Python.
        # The LLM no longer fetches/merges/recommits files by hand (the old fragile
        # flow that silently corrupted files on a snippet mismatch).
        tools=[apply_remediation_plan, github_apply_remediation_plan, bitbucket_apply_remediation_plan],
        # include_contents defaults to 'all' — required for multi-turn tool calling
        generate_content_config=_cfg.generation_config(_cfg.agent_settings.remediation_temperature),
        before_agent_callback=_executor_before_callback,
        after_agent_callback=_executor_after_callback,
        before_tool_callback=block_github_misuse,
        before_model_callback=_executor_before_model_callback,
    )


remediation_executor = _make_executor("remediation_executor")

# ---------------------------------------------------------------------------
# Workflow nodes
# ---------------------------------------------------------------------------


async def _remediation_gate_callback(ctx) -> Event:
    """
    Determines if remediation should be attempted based on user request and config.
    """
    user_request = ctx.state.get("user_request", "")
    is_remote = "github.com" in user_request.lower() or "bitbucket.org" in user_request.lower()

    # Also pass if the reviewed repo is already known from state (e.g. approval-resume
    # turn where user_request is a sentinel, not the original GitHub URL).
    owner = str(ctx.state.get("authorized_github_owner") or "").strip()
    repo = str(ctx.state.get("authorized_github_repo") or "").strip()
    has_reviewed_repo = bool(owner and repo)

    current_config = Config()
    if not is_remote and not current_config.github_remediation_repo and not has_reviewed_repo:
        logger.info("remediation_gate: No remote source or default repo. Skipping remediation.")
        ctx.state["remediation_skipped"] = True
        return Event(output="Remediation skipped (No target repository defined).", route="skip")

    return Event(route="plan")

remediation_gate = FunctionNode(name="remediation_gate", func=_remediation_gate_callback)


async def _remediation_gate_skip_callback(ctx) -> None:
    """Terminal no-op for skipped remediation (a route must point at a node)."""
    return None

remediation_gate_skip = FunctionNode(name="remediation_gate_skip", func=_remediation_gate_skip_callback)


# ---------------------------------------------------------------------------
# Combined Remediation Workflow
# Expose as a single unit to agent.py
# ---------------------------------------------------------------------------
remediation_agent = Workflow(
    name="remediation_agent",
    description=(
        "Full remediation pipeline: plans code changes from synthesis report "
        "then executes them as a GitHub PR via the GitHub MCP API."
    ),
    edges=[
        (START, remediation_gate),
        # Research the ADK docs FIRST, then plan, then execute. The research node
        # writes adk_remediation_context, which the planner injects into its prompt.
        (remediation_gate, {"plan": remediation_research_r, "skip": remediation_gate_skip}),
        (remediation_research_r, remediation_planner),
        (remediation_planner, remediation_executor),
    ],
)


# ---------------------------------------------------------------------------
# Approval-resume workflow (Human-in-the-Loop)
#
# When the main pipeline pauses remediation for approval, the saved
# `remediation_plan` stays in session state. The frontend's Approve/Skip buttons
# send a sentinel message; the supervisor sets `remediation_approved` /
# `remediation_skipped` (constitution_callback) and transfers here. This flow
# runs ONLY the executor against the already-approved plan — it does not re-plan,
# so the user gets exactly the PR they reviewed.
# ---------------------------------------------------------------------------
remediation_resume_executor = _make_executor("remediation_resume_executor")

remediation_resume_flow = Workflow(
    name="remediation_resume_flow",
    description=(
        "Resumes a remediation awaiting approval: creates the PR from the saved "
        "plan when approved, or marks it skipped — without re-planning."
    ),
    edges=[
        (START, remediation_resume_executor),
    ],
)
