from __future__ import annotations

"""
Revision Agent — Self-improvement step inside the Workflow.

Role in Pipeline:
When `evaluation_expert` returns FAIL, this agent reads the auditor feedback
from state and rewrites the weakest expert's review. Its output is dynamically routed
back to the same state key as the original failing review via a callback.
This ensures the `synthesis_agent` receives the improved version transparently.

State Interactions:
- Reads: `failing_review_content`, `evaluation_result`, `code_logic`, `confluence_rules`, `failing_review_key`
- Writes: `revised_review_content` (which is then copied into the failing review's state key)
"""

import logging
from google.adk.agents import LlmAgent
from agent_guardian.config import Config
from agent_guardian.prompts import REVISION_REQUEST_PROMPT
from ..utils.loop_state import LoopState
from ..utils.token_utils import synthesis_budget_callback

logger = logging.getLogger(__name__)
_cfg = Config()


# ---------------------------------------------------------------------------
# Dynamic output_key callback — routes revised review to the correct state key
# ---------------------------------------------------------------------------
from google.adk.agents.callback_context import CallbackContext


async def _route_revision_output(callback_context: CallbackContext):
    """
    Before the revision agent runs, determine which state key to write to
    by reading the 'failing_review_key' stored by evaluation_expert's callback.
    ADK does not support dynamic output_key at runtime, so we handle the
    routing manually in the after_agent_callback instead.

    Now also applies synthesis_budget_callback to protect from large inputs.
    """
    await synthesis_budget_callback(callback_context)


def _persist_revised_review(callback_context: CallbackContext):
    """
    After the revision agent writes to 'revised_review_content', copy the
    result back to the original failing review's state key so the synthesis
    agent sees the improved version.
    """
    target_key = callback_context.state.get("failing_review_key", "")
    if not target_key:
        loop = LoopState.read(callback_context.state)
        loop.request_exit("failing_review_key missing — cannot route revision")
        loop.write(callback_context.state)
        logger.warning(
            "revision_agent: failing_review_key is empty or missing. Forcing loop exit to prevent infinite spin."
        )
        return

    revised = callback_context.state.get("revised_review_content", "")

    if revised and target_key:
        callback_context.state[target_key] = revised
        logger.info(f"revision_agent: persisted improved review → state['{target_key}'] ({len(revised)} chars)")
    else:
        logger.warning(
            f"revision_agent: could not persist revised review (revised={bool(revised)}, target_key='{target_key}')"
        )


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

revision_agent = LlmAgent(
    model=_cfg.agent_settings.evaluation_model,  # Same tier as evaluation expert
    name="revision_agent",
    description=(
        "Self-improvement agent: rewrites the weakest expert's review based on "
        "structured feedback from the evaluation_expert. Runs inside the LoopAgent."
    ),
    instruction=REVISION_REQUEST_PROMPT,
    output_key="revised_review_content",  # Written to state; callback routes to correct key
    include_contents="none",  # All context from state injection
    generate_content_config=_cfg.safety_config,
    before_agent_callback=_route_revision_output,
    after_agent_callback=_persist_revised_review,
)
