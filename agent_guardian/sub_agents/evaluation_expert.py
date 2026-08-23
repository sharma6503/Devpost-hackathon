from __future__ import annotations

"""
Evaluation Expert — In-pipeline Quality Gate.

Role in Pipeline:
Scores all expert reviews on three dimensions (Specificity, Evidence, Actionability).
Runs inside a Workflow in `agent.py`. On PASS, sets a state flag to exit the loop.
On FAIL, stores structured feedback so `revision_agent` can self-revise the weakest review.

Pattern: quality_gate_loop (Workflow)
  ├── parallel_review_experts # writes expert results to state (runs ONCE)
  └── revision_loop (Workflow Cycle)
      ├── evaluation_expert    # scores results; exits loop on PASS
      ├── quality_gate_router  # routes to pass (synthesis) or fail (revision)
      └── revision_agent       # rewrites weakest review on FAIL

State Interactions:
- Reads: `adk_review_result`, `quality_review_result`, `security_review_result`, `governance_review_result`, `validation_result`
- Writes: `evaluation_result` (JSON), `evaluation_grade`, `evaluation_feedback`, `weakest_agent`, `failing_review_content`, `failing_review_key`, `temp:quality_gate` (LoopState)
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from agent_guardian.config import Config, _env_int
from agent_guardian.models import EvaluationResult  # ← from shared models package
from agent_guardian.prompts import EVALUATION_EXPERT_PROMPT
from .registry import AGENT_NAME_TO_STATE_KEY, normalize_expert_name
from ..utils.loop_state import LoopState
from ..utils.token_utils import synthesis_budget_callback
from ..utils.json_parse import parse_json_into_model
from ..utils.markdown_format import format_evaluation_md

logger = logging.getLogger(__name__)
_cfg = Config()


# ---------------------------------------------------------------------------
# Post-agent callback: parse result, store feedback, signal loop exit
# ---------------------------------------------------------------------------


def _evaluation_after_callback(callback_context: CallbackContext):
    """
    Parses the EvaluationResult JSON from state, stores actionable feedback
    for the weakest expert, and requests loop exit via LoopState on PASS
    so the LoopAgent can exit cleanly.

    Runs AFTER evaluation_expert writes to state['evaluation_result'].
    """
    raw = callback_context.state.get("evaluation_result", "")
    if not raw:
        logger.warning("evaluation_expert: no output found in state['evaluation_result'].")
        return

    result = parse_json_into_model(raw, EvaluationResult, context="evaluation_expert")
    if result is None:
        loop = LoopState.read(callback_context.state)
        loop.parse_failures += 1
        if loop.parse_failures >= 3:
            loop.request_exit("evaluation output unparseable after 3 attempts")
            callback_context.state["evaluation_grade"] = "FORCE_EXIT"
        loop.write(callback_context.state)
        return

    logger.info(
        f"Evaluation: grade={result.overall_grade} | weakest={result.weakest_agent} ({result.weakest_dimension})"
    )

    # Persist structured state for revision_agent and orchestration
    callback_context.state["evaluation_grade"] = result.overall_grade
    callback_context.state["evaluation_feedback"] = result.feedback
    callback_context.state["weakest_agent"] = result.weakest_agent or ""

    # Format Markdown representation
    md_text = format_evaluation_md(result)
    callback_context.state["evaluation_result_md"] = md_text

    # Map agent name → its state key so revision_agent knows where to write
    # (single source of truth: sub_agents/registry.py)
    if result.weakest_agent:
        normalized = normalize_expert_name(result.weakest_agent)
        failing_key = AGENT_NAME_TO_STATE_KEY.get(result.weakest_agent) or AGENT_NAME_TO_STATE_KEY.get(normalized)
        if failing_key:
            callback_context.state["failing_review_content"] = callback_context.state.get(failing_key, "")
            callback_context.state["failing_review_key"] = failing_key
        else:
            logger.warning(
                f"evaluation_expert: weakest_agent '{result.weakest_agent}' (normalized: '{normalized}') not in AGENT_NAME_TO_STATE_KEY. "
                f"Known: {list(AGENT_NAME_TO_STATE_KEY.keys())}"
            )

    # Signal the quality-gate router to stop when grade is PASS
    if not result.remediation_required:
        logger.info("evaluation_expert: PASS — requesting loop exit.")
        loop = LoopState.read(callback_context.state)
        loop.request_exit("evaluation PASS")
        loop.write(callback_context.state)

    return None


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

_threshold = _cfg.agent_settings.eval_pass_threshold

# EvaluationResult embeds per-expert scores + feedback (which quotes review text),
# so it overflows the default ~8192 ceiling and truncates the JSON. ADK validates
# output_schema in __maybe_save_output_to_state BEFORE our after-callback runs, so
# a cut-off JSON string raises a ValidationError that aborts the whole node — it
# cannot be recovered by the parse-failure guard below. Give it headroom.
# Mirrors the remediation_planner override.
_eval_config = _cfg.generation_config(temperature=_cfg.agent_settings.evaluation_temperature)
_eval_config.max_output_tokens = _env_int("EVALUATION_MAX_OUTPUT_TOKENS", 16384)

evaluation_expert = LlmAgent(
    model=_cfg.agent_settings.evaluation_model,
    name="evaluation_expert",
    description=(
        "Quality gate: scores all expert reviews on Specificity, Evidence, and Actionability. "
        "Exits the LoopAgent on PASS; stores structured feedback for revision_agent on FAIL."
    ),
    instruction=EVALUATION_EXPERT_PROMPT.replace("{eval_pass_threshold}", str(_threshold)),
    output_key="evaluation_result",  # ADK persists JSON string to state
    output_schema=EvaluationResult,  # Forces structured JSON — disables tool calls on this agent
    include_contents="none",  # Stateless: all input comes from state injection
    before_agent_callback=synthesis_budget_callback,
    # Low temperature: scoring must be deterministic run-to-run.
    generate_content_config=_eval_config,
    after_agent_callback=_evaluation_after_callback,
    # NOTE: output_schema disables tool use (ADK limitation).
    # Loop exit is signalled via LoopState (state['temp:quality_gate']) in the callback above.
)
