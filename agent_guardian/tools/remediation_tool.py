from __future__ import annotations

import json
import logging
from agent_guardian.tools.github_tool import github_apply_remediation_plan
from agent_guardian.tools.bitbucket_tool import bitbucket_apply_remediation_plan

logger = logging.getLogger(__name__)


def _coerce_plan_dict(plan_val: any) -> dict:
    if plan_val is None:
        return {}
    if isinstance(plan_val, dict):
        return dict(plan_val)
    if hasattr(plan_val, "model_dump") and callable(plan_val.model_dump):
        return plan_val.model_dump()
    if hasattr(plan_val, "dict") and callable(plan_val.dict):
        return plan_val.dict()
    if isinstance(plan_val, str) and plan_val.strip():
        try:
            parsed = json.loads(plan_val)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


async def apply_remediation_plan(
    plan: dict | None = None,
    tool_context=None,
) -> dict:
    """Deterministically apply a RemediationPlan to the target repository (GitHub or Bitbucket) and open a PR.

    Automatically resolves whether the target repository is GitHub or Bitbucket Cloud based on
    the target repository URL, state context, and plan parameters.
    """
    state = getattr(tool_context, "state", {}) or {}
    user_req = str(state.get("user_request", "") or "").lower()
    prev_user_req = str(state.get("_previous_user_request", "") or "").lower()

    # Read plan from arguments or state
    raw_plan = _coerce_plan_dict(plan)
    if not raw_plan and tool_context is not None:
        raw_plan = _coerce_plan_dict(state.get("remediation_plan"))

    target_repo = str(raw_plan.get("target_repo", "") or "").lower()

    # Detect if target or source was Bitbucket
    is_bitbucket = (
        "bitbucket.org" in user_req
        or "bitbucket.org" in prev_user_req
        or "bitbucket" in target_repo
        or bool(state.get("is_bitbucket"))
        or bool(state.get("authorized_bitbucket_workspace"))
    )

    if is_bitbucket:
        logger.info("[apply_remediation_plan] Dispatching to Bitbucket remediation tool.")
        return await bitbucket_apply_remediation_plan(plan=raw_plan, tool_context=tool_context)
    else:
        logger.info("[apply_remediation_plan] Dispatching to GitHub remediation tool.")
        return await github_apply_remediation_plan(plan=raw_plan, tool_context=tool_context)
