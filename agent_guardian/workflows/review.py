from __future__ import annotations

"""
Workflow definitions and node routing for Agent Guardian.

Defines review_pipeline (Workflow), WorkflowAgent, and remediation_resume_agent.
"""

import logging
import asyncio
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext, Context
from google.adk.workflow import Workflow, START, JoinNode, FunctionNode
from google.adk import Event
from google.adk.agents.callback_context import CallbackContext

from agent_guardian.config import Config
from agent_guardian.utils.resilience import (
    resilient,
    harden_node,
    safe_callback,
)
from agent_guardian.utils.token_utils import synthesis_budget_callback
from agent_guardian.sub_agents.adk_expert import adk_expert_preflight as _adk_preflight
from agent_guardian.utils.callbacks import pacing_callback

from agent_guardian.sub_agents import (
    ingestion_agent,
    governance_expert,
    adk_expert,
    quality_expert,
    security_expert,
    code_validator_agent,
    synthesis_agent,
    metrics_agent,
    html_agent,
    confluence_rules_agent,
    evaluation_expert,
    revision_agent,
    remediation_agent,
    remediation_resume_flow,
    planning_agent,
)

logger = logging.getLogger(__name__)
configs = Config()


class WorkflowAgent(BaseAgent):
    """Wraps a Workflow to be used as a BaseAgent."""

    workflow: Workflow

    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Initialize event queue if not present (legacy path)
        queue_owner = False
        if ctx._event_queue is None:
            ctx._event_queue = asyncio.Queue()
            queue_owner = True

        # Wrap InvocationContext into a Context to run the workflow
        wf_ctx = Context(invocation_context=ctx)

        if queue_owner:
            # We must drain the queue as we run the workflow.
            # NodeRunners inside the workflow will enqueue events into ctx._event_queue.
            async def run_wf():
                try:
                    async for _ in self.workflow.run(ctx=wf_ctx, node_input=None):
                        pass
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # Never re-raise: a workflow-orchestration failure must not crash
                    # the whole run. Node-level resilience (ResilientAgent / RetryConfig)
                    # already degrades individual nodes; here we log and end so the run
                    # finishes with whatever (partial) report state exists.
                    logger.error(
                        f"Workflow execution failed; ending run gracefully: {e}",
                        exc_info=True,
                    )

            wf_task = asyncio.create_task(run_wf())

            try:
                while not wf_task.done() or not ctx._event_queue.empty():
                    try:
                        # Wait for an event with a timeout to check task status periodically
                        item = await asyncio.wait_for(ctx._event_queue.get(), timeout=0.1)
                        event, processed = item
                        yield event
                        if processed:
                            processed.set()
                    except asyncio.TimeoutError:
                        continue
            finally:
                if not wf_task.done():
                    wf_task.cancel()
                    try:
                        await wf_task
                    except asyncio.CancelledError:
                        pass
                else:
                    try:
                        exc = wf_task.exception()
                        if exc is not None:
                            logger.error(f"Workflow task ended with exception: {exc}")
                    except asyncio.CancelledError:
                        pass
        else:
            # Standard path: someone else is draining the queue (e.g. Runner)
            try:
                async for event in self.workflow.run(ctx=wf_ctx, node_input=None):
                    yield event
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    f"Workflow execution failed; ending run gracefully: {e}",
                    exc_info=True,
                )


# ---------------------------------------------------------------------------
# Workflow Nodes & Routing
# ---------------------------------------------------------------------------


async def _pre_review_reset_callback(ctx) -> None:
    """Guarantees a clean slate at the start of EVERY review."""
    try:
        from agent_guardian.state import reset_review_state

        current_request = ctx.state.get("user_request", "")
        reset_review_state(ctx.state)
        ctx.state["_previous_user_request"] = current_request

        # Heal cross-run singletons
        try:
            from agent_guardian.utils.mcp_factory import invalidate_mcp_toolsets

            invalidate_mcp_toolsets()
        except Exception as e:
            logger.warning(f"[pre_review_reset_node] MCP toolset invalidation skipped: {e}")
        try:
            from agent_guardian.utils.token_utils import (
                expert_token_manager,
                synthesis_token_manager,
            )

            expert_token_manager.reset()
            synthesis_token_manager.reset()
        except Exception as e:
            logger.warning(f"[pre_review_reset_node] token manager reset skipped: {e}")
    except Exception as e:
        logger.error(f"[pre_review_reset_node] state reset failed (continuing): {e}")

pre_review_reset_node = FunctionNode(name="pre_review_reset_node", func=_pre_review_reset_callback)


async def _merge_local_skills_callback(ctx) -> None:
    """Merges GCP Skill Registry standards with the retrieved Confluence rules."""
    try:
        from agent_guardian.utils.skill_loader import fetch_configured_gcp_skills, get_merged_ruleset

        confluence_rules = ctx.state.get("confluence_rules", "")
        configured_skills = ctx.state.get("gcp_skills") or ctx.state.get("skills") or ctx.state.get("skill_names")
        if isinstance(configured_skills, str):
            configured_skills = [s.strip() for s in configured_skills.split(",") if s.strip()]

        search_queries = ctx.state.get("skill_search_queries")
        if isinstance(search_queries, str):
            search_queries = [search_queries]

        skills = await fetch_configured_gcp_skills(
            skill_names=configured_skills,
            search_queries=search_queries,
        )

        merged_rules = await get_merged_ruleset(
            confluence_rules=confluence_rules,
            skills=skills,
        )
        ctx.state["confluence_rules"] = merged_rules

        # Persist retrieved skills metadata in state for downstream tracking and reporting
        retrieved_meta = [
            {"name": s.name, "description": getattr(s, "description", "") or getattr(getattr(s, "frontmatter", None), "description", "")}
            for s in skills
        ]
        ctx.state["retrieved_gcp_skills"] = retrieved_meta
        logger.info(
            "[merge_local_skills_node] Successfully integrated %d GCP skill(s) into confluence_rules: %s",
            len(skills),
            [s.name for s in skills],
        )
    except Exception as e:
        logger.error(f"[merge_local_skills_node] Failed to merge GCP skills (continuing): {e}")

merge_local_skills_node = FunctionNode(name="merge_local_skills_node", func=_merge_local_skills_callback)


async def _quality_gate_router_callback(ctx) -> Event:
    """Evaluates outcomes of evaluation_expert and loops or routes to synthesis."""
    try:
        from agent_guardian.utils.loop_state import LoopState

        loop = LoopState.read(ctx.state)
        loop.iterations += 1
        loop.write(ctx.state)

        max_iters = configs.agent_settings.eval_max_iterations
        logger.info(f"[quality_gate_router] Evaluation loop iteration {loop.iterations}/{max_iters}")

        if loop.exit_requested or loop.iterations >= max_iters:
            if loop.exit_requested:
                logger.info(f"[quality_gate_router] Exit requested: {loop.exit_reason or 'unspecified'}.")
            else:
                logger.info(f"[quality_gate_router] Reached max loop iterations ({max_iters}). Forcing pass.")
            return Event(route="pass")
        else:
            logger.info("[quality_gate_router] Quality gate failed. Routing to revision_agent.")
            return Event(route="fail")
    except Exception as e:
        logger.error(f"[quality_gate_router] failed (forcing pass): {e}")
        return Event(route="pass")

quality_gate_router = FunctionNode(name="quality_gate_router", func=_quality_gate_router_callback)


async def _remediation_router_callback(ctx) -> Event:
    """Runs remediation only when the audit found high/critical issues."""
    try:
        metrics = ctx.state.get("review_metrics") or {}
        if hasattr(metrics, "model_dump"):
            metrics = metrics.model_dump()
        severity = metrics.get("severity") if isinstance(metrics, dict) else None
        severity = severity if isinstance(severity, dict) else {}
        try:
            actionable = int(severity.get("critical", 0) or 0) + int(severity.get("high", 0) or 0)
        except (TypeError, ValueError):
            actionable = 0

        if actionable > 0:
            logger.info(f"[remediation_router] {actionable} high/critical findings — running remediation.")
            return Event(route="remediate")

        ctx.state["remediation_skipped"] = True
        logger.info("[remediation_router] No high/critical findings — skipping remediation.")
        return Event(route="skip")
    except Exception as e:
        logger.error(f"[remediation_router] failed (skipping remediation): {e}")
        return Event(route="skip")

remediation_router = FunctionNode(name="remediation_router", func=_remediation_router_callback)


async def _remediation_skip_callback(ctx) -> None:
    """Terminal no-op for clean audits."""
    return None

remediation_skip_node = FunctionNode(name="remediation_skip_node", func=_remediation_skip_callback)


async def _ingestion_gate_router_callback(ctx) -> Event:
    """Abort pipeline early when ingestion produced no usable files."""
    try:
        code_logic = ctx.state.get("code_logic", "") or ""
        if code_logic.lstrip().startswith("[INGESTION_FAILED]"):
            logger.warning("[ingestion_gate_router] Ingestion failed — aborting pipeline.")
            return Event(route="abort")
        return Event(route="ok")
    except Exception as e:
        logger.error(f"[ingestion_gate_router] check failed (continuing): {e}")
        return Event(route="ok")

ingestion_gate_router = FunctionNode(name="ingestion_gate_router", func=_ingestion_gate_router_callback)


async def _ingestion_failed_callback(ctx) -> None:
    """Terminal node: writes user-facing error into report state keys."""
    try:
        code_logic = ctx.state.get("code_logic", "") or ""
        _PREFIX = "[INGESTION_FAILED] "
        detail = code_logic[len(_PREFIX) :].strip() if code_logic.startswith(_PREFIX) else code_logic[:500]

        error_md = (
            "## Ingestion Failed\n\n"
            "The review pipeline could not start because no source files were ingested.\n\n"
            f"**Reason:** {detail}\n\n"
            "**What to check:**\n"
            "- For GitHub/Bitbucket URLs: confirm the repo is accessible and your token has read permission.\n"
            "- For ZIP uploads: confirm the archive contains at least one source file (`.py`, `.ts`, `.js`, etc.).\n"
            "- Repository 404 errors usually mean the URL is wrong or the repo is private without a valid token.\n\n"
            "Please fix the issue and retry the review."
        )
        ctx.state["synthesis_result"] = error_md
        ctx.state["html_report"] = (
            "<html><body style='font-family:system-ui;padding:40px;max-width:800px;margin:auto'>"
            "<h1 style='color:#b91c1c'>Ingestion Failed</h1>"
            f"<p>{detail}</p>"
            "<p>The review could not run. Check repository access and retry.</p>"
            "</body></html>"
        )
        ctx.state["review_metrics"] = {}
        ctx.state["ingestion_error"] = detail
        logger.info("[ingestion_failed_node] Error state written; pipeline terminated cleanly.")
    except Exception as e:
        logger.error(f"[ingestion_failed_node] failed to write error state: {e}")

ingestion_failed_node = FunctionNode(name="ingestion_failed_node", func=_ingestion_failed_callback)


# ---------------------------------------------------------------------------
# Expert Fleet Orchestration
# ---------------------------------------------------------------------------

_ALL_EXPERTS = [
    adk_expert,
    quality_expert,
    security_expert,
    governance_expert,
    code_validator_agent,
]


@safe_callback
async def _expert_preflight(callback_context: CallbackContext):
    await synthesis_budget_callback(callback_context)
    await pacing_callback(callback_context)


@safe_callback
async def _adk_expert_preflight(callback_context: CallbackContext):
    await synthesis_budget_callback(callback_context)
    await _adk_preflight(callback_context)
    await pacing_callback(callback_context)


for _exp in _ALL_EXPERTS:
    if _exp is adk_expert:
        _exp.before_agent_callback = _adk_expert_preflight
    else:
        _exp.before_agent_callback = _expert_preflight


# Transient-retry for single-chain / composite nodes
for _node_agent in (
    ingestion_agent,
    confluence_rules_agent,
    planning_agent,
    evaluation_expert,
    revision_agent,
    remediation_agent,
):
    harden_node(_node_agent)


_PLANNING_FALLBACK_STATE = {
    "review_plan": {
        "is_large_codebase": False,
        "strategy": "Fallback default: all experts perform standard full review of the ingested files.",
        "assignments": [
            {
                "expert_name": exp,
                "assigned_modules": ["all"],
                "focus_areas": "Standard audit review (planning agent fallback).",
            }
            for exp in (
                "quality_expert",
                "security_expert",
                "governance_expert",
                "adk_expert",
                "code_validator_agent",
            )
        ],
    },
    "review_plan_md": "### Review Plan (Fallback)\nAll experts assigned to review the entire codebase.",
}
planning_agent_r = resilient(planning_agent, fallback_state=_PLANNING_FALLBACK_STATE)

_EVALUATION_FALLBACK_STATE = {
    "evaluation_grade": "PASS",
    "evaluation_feedback": "Automated evaluation fallback: passing to synthesis.",
    "weakest_agent": "",
}
evaluation_expert_r = resilient(evaluation_expert, fallback_state=_EVALUATION_FALLBACK_STATE)
revision_agent_r = resilient(revision_agent, fallback_text="Revision completed (fallback).")
remediation_agent_r = resilient(remediation_agent, fallback_text="Remediation skipped (fallback).")

_EXPERT_FALLBACK = (
    "[SYSTEM_NOTE: Analysis skipped] This expert could not complete after "
    "repeated retries; the remaining experts' findings are still valid."
)
quality_expert_r = resilient(quality_expert, fallback_text=_EXPERT_FALLBACK)
security_expert_r = resilient(security_expert, fallback_text=_EXPERT_FALLBACK)
adk_expert_r = resilient(adk_expert, fallback_text=_EXPERT_FALLBACK)
governance_expert_r = resilient(governance_expert, fallback_text=_EXPERT_FALLBACK)
code_validator_agent_r = resilient(code_validator_agent, fallback_text=_EXPERT_FALLBACK)

synthesis_agent_r = resilient(
    synthesis_agent,
    fallback_text=(
        "## Synthesis Unavailable\n\nThe synthesis step failed after multiple "
        "retries. Individual expert findings remain available in their sections."
    ),
)
metrics_agent_r = resilient(metrics_agent, fallback_state={"review_metrics": {}})
html_agent_r = resilient(
    html_agent,
    fallback_text=(
        "<html><body style='font-family:system-ui;padding:40px'>"
        "<h1>Report generation incomplete</h1>"
        "<p>The HTML report could not be assembled after multiple retries. "
        "The underlying expert reviews are still available in the audit results.</p>"
        "</body></html>"
    ),
)

ingest_rules_join = JoinNode(name="ingest_rules_join")
experts_join = JoinNode(name="experts_join")

review_pipeline = Workflow(
    name="review_pipeline",
    edges=[
        (START, pre_review_reset_node),
        (pre_review_reset_node, (ingestion_agent, confluence_rules_agent)),
        ((ingestion_agent, confluence_rules_agent), ingest_rules_join),
        (ingest_rules_join, ingestion_gate_router),
        (ingestion_gate_router, {"ok": merge_local_skills_node, "abort": ingestion_failed_node}),
        (merge_local_skills_node, planning_agent_r),
        (
            planning_agent_r,
            (
                quality_expert_r,
                security_expert_r,
                adk_expert_r,
                governance_expert_r,
                code_validator_agent_r,
            ),
        ),
        (
            (
                quality_expert_r,
                security_expert_r,
                adk_expert_r,
                governance_expert_r,
                code_validator_agent_r,
            ),
            experts_join,
        ),
        (experts_join, evaluation_expert_r),
        (evaluation_expert_r, quality_gate_router),
        (quality_gate_router, {"pass": synthesis_agent_r, "fail": revision_agent_r}),
        (revision_agent_r, evaluation_expert_r),
        (synthesis_agent_r, metrics_agent_r),
        (metrics_agent_r, html_agent_r),
        (html_agent_r, remediation_router),
        (
            remediation_router,
            {"remediate": remediation_agent, "skip": remediation_skip_node},
        ),
    ],
)

review_pipeline_agent = WorkflowAgent(name="review_pipeline", workflow=review_pipeline)
remediation_resume_agent = WorkflowAgent(name="remediation_resume_agent", workflow=remediation_resume_flow)
