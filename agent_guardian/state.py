from __future__ import annotations
import json
import logging
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, Union
from agent_guardian.models import (
    EvaluationResult,
    ReviewMetrics,
    RemediationPlan,
    ReviewPlan,
)

logger = logging.getLogger(__name__)


def _coerce_structured(value: Any) -> Any:
    """Normalize Union[Model, dict, str] fields toward dict before validation.

    LLM agents persist their output_key as a JSON string (often inside markdown
    fences); callbacks may later overwrite it with a dict or a Pydantic model.
    Parsing here means every consumer sees a dict/model, never a raw JSON
    string. Unparseable strings (error sentinels like "[SYSTEM_NOTE: ...]")
    pass through unchanged — that is part of their contract.
    """
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.debug("ReviewState: structured field held a non-JSON string; leaving as-is.")
    return value


class ReviewState(BaseModel):
    """Formalized state schema for the Agent Guardian Session."""

    @field_validator(
        "review_plan",
        "evaluation_result",
        "review_metrics",
        "remediation_plan",
        mode="before",
    )
    @classmethod
    def _normalize_structured_fields(cls, v: Any) -> Any:
        return _coerce_structured(v)

    @classmethod
    def from_session_state(cls, state: Any) -> "ReviewState":
        """Build a validated ReviewState from a session-state mapping,
        ignoring unknown keys (temp:, private, scratch keys)."""
        known = set(cls.model_fields)
        data = {k: v for k, v in dict(state).items() if k in known}
        return cls(**data)

    # Core Request
    user_request: str = ""
    _previous_user_request: str = ""
    authorized_github_owner: str = ""
    authorized_github_repo: str = ""
    authorized_github_ref: str = ""

    # Caller identity from the login form, seeded into session state at creation
    # (frontend createSession initialState). Session-constant — preserved across
    # per-review resets (see _PRESERVE_KEYS) so every audit in the session keeps
    # them. NOTE: user-claimed unless backed by real auth — do NOT gate access on
    # these without an upstream identity provider.
    user_department: str = ""
    user_country: str = ""

    # Follow-up Q&A (post-review conversation). The follow-up question is stored
    # HERE and never in `user_request`, so a follow-up runs through followup_agent
    # (outside the review pipeline) and never hits pre_review_reset_node, which
    # would otherwise wipe the completed review the user is asking about.
    followup_question: str = ""
    followup_answer: str = ""

    # Codebase Context
    raw_codebase: str = ""
    source_artifact_path: str = ""
    code_logic: str = ""
    code_config: str = ""
    code_docs: str = ""
    is_large_codebase: bool = False
    module_map: Dict[str, Any] = Field(default_factory=dict)
    logic_file_count: int = 0
    total_file_count: int = 0
    # Ingestion coverage transparency (populated from github_ingest_repository):
    # files deliberately excluded (binary/over-budget) and whether the Git tree
    # was truncated and recovered via a Contents-API walk. Lets the UI/synthesis
    # report coverage honestly instead of implying 100% when files were dropped.
    ingest_skipped: list = Field(default_factory=list)
    ingest_truncated: bool = False

    # Ingestion & Uploads
    uploaded_zip_path: str = ""

    # Constitution & Rules
    constitution: str = "Be professional and concise."
    confluence_rules: str = (
        "[CONFLUENCE_UNAVAILABLE] No Confluence rules fetched. "
        "Use built-in baselines and DO NOT claim Confluence validation."
    )
    confluence_pages_index: str = ""
    confluence_host_map_json: str = ""

    # GCP Skills & Extensions (from gcp_skill_pull / skills retrieval)
    retrieved_gcp_skills: Optional[list] = None
    gcp_skills: Optional[list] = None
    skills: Optional[list] = None
    skill_search_queries: Optional[list] = None

    # Review Plan (from planning_agent)
    review_plan: Optional[Union[ReviewPlan, Dict[str, Any], str]] = None

    # Review Results (Raw Markdown from Experts)
    governance_review_result: str = "Not provided or skipped."
    adk_review_result: str = "Not provided or skipped."
    quality_review_result: str = "Not provided or skipped."
    security_review_result: str = "Not provided or skipped."
    validation_result: str = "Not provided or skipped."

    # Quality Gate / Evaluation (Structured)
    synthesis_result: str = "Not provided or skipped."
    critic_feedback: str = "Not provided or skipped."
    evaluation_result: Optional[Union[EvaluationResult, Dict[str, Any], str]] = None
    evaluation_grade: str = "Not provided or skipped."
    evaluation_feedback: str = "Not provided or skipped."
    weakest_agent: str = "Not provided or skipped."
    failing_review_content: str = "Not provided or skipped."
    failing_review_key: str = "Not provided or skipped."
    revised_review_content: str = "Not provided or skipped."
    # NOTE: loop-control flags live in state["temp:quality_gate"] (LoopState),
    # not here — temp-scoped state is cleared per invocation, which matches
    # the loop's lifetime.

    # Reporting (Structured)
    review_metrics: Optional[Union[ReviewMetrics, Dict[str, Any], str]] = None
    html_report_content: str = ""
    scorecard_html: str = ""
    repo_metadata_html: str = ""
    expert_reviews_html: str = ""

    # Remediation (Structured)
    # ADK/Gemini doc-grounded notes produced by remediation_research before the
    # planner writes code, so generated fixes cite verified APIs (not memory).
    adk_remediation_context: str = "Not provided or skipped."
    remediation_plan: Optional[Union[RemediationPlan, Dict[str, Any], str]] = None
    remediation_pr_url: str = ""
    remediation_skipped: bool = False
    # Lifecycle status for the remediation stage, kept SEPARATE from the URL so a
    # status/pending message is never rendered (or linked) as a PR URL. One of:
    # "" (not run), "pending_approval", "created", "skipped", "dry_run",
    # "no_target", "failed". remediation_pr_url holds an http(s) URL ONLY.
    remediation_status: str = ""
    remediation_pending_approval: bool = False
    remediation_plan_summary: str = ""
    remediation_commit_id: str = ""
    # Changes the deterministic apply tool could NOT safely commit (snippet not
    # found / ambiguous match / fetch error). Surfaced so the UI can show partial
    # remediation honestly instead of silently dropping unapplied fixes.
    remediation_failed_changes: list = Field(default_factory=list)

    # Live Model Lifecycle (populated by adk_expert via get_model_lifecycle tool)
    model_lifecycle_data: Optional[list] = None

    # Tracking
    metadata_agent_calls: int = 0
    _429_retry_count: int = 0


# ---------------------------------------------------------------------------
# Per-review state reset
# ---------------------------------------------------------------------------

# Keys that must survive a reset (they identify the request, not its results).
_PRESERVE_KEYS = {
    "user_request",
    "_previous_user_request",
    "authorized_github_owner",
    "authorized_github_repo",
    "authorized_github_ref",
    "remediation_commit_id",
    # Session-constant caller identity — seeded once at session creation; must
    # survive every per-review reset or it's lost after the first audit.
    "user_department",
    "user_country",
    # Configuration and uploaded asset paths that identify current turn/session
    "uploaded_zip_path",
    "confluence_host_map_json",
    "gcp_skills",
    "skills",
    "skill_search_queries",
    "retrieved_gcp_skills",
}

# Run-scoped keys written OUTSIDE ReviewState's public schema (so absent from
# model_dump()) that would otherwise bleed from one review into the next:
#   - dynamic artifacts/notes written by ingestion / file interception
#   - the 429 pacing counters (one private attr, one temp key)
# NOTE: authorized_github_owner/repo are preserved through pipeline resets so the
# tool guard (block_github_wrong_repo) can enforce repo scoping inside the pipeline.
# constitution_callback sets them before root_agent runs; they must survive
# pre_review_reset_node or every expert agent would see empty values and the
# guard would silently allow calls to any GitHub repo (tool_guards.py:91-92).
# NOTE: uploaded_zip_path is deliberately NOT purged here. It is a CURRENT-TURN
# signal that constitution_callback sets (or clears) from the live user_content,
# and that callback runs BEFORE this reset. Purging it here would wipe the freshly
# uploaded ZIP before ingestion/the upload guard can read it — the exact ordering
# bug behind "a new upload relies on previously uploaded files".
_ORPHAN_KEYS = {
    "mcp_environment_warning",
    "pre_flight_governance_scan",
    "_429_retry_count",
    "temp:429_retry_count",
    # Raw text the remediation executor writes via output_key; the after-callback
    # distills it into remediation_pr_url/remediation_status. Run-scoped scratch.
    "remediation_executor_raw",
    "remediation_approved",
    # Verbatim source snippets prefetched by remediation_planner's before-callback
    # (_planner_before_callback). Run-scoped: a prior review's source must not bleed
    # into the next review's planner prompt.
    "remediation_source_context",
}
_ORPHAN_PREFIXES = ("confluence_page_",)


def reset_review_state(state: Any) -> None:
    """Restore every ReviewState field to its default and purge run-scoped keys.

    Idempotent and safe to call on EVERY pipeline entry — this is what makes the
    Nth review behave identically to the 1st. Never raises: a failure here must
    degrade (continue with existing state), not abort the run.
    """
    if state is None:
        return

    try:
        defaults = ReviewState().model_dump()
        for key, default_val in defaults.items():
            if key not in _PRESERVE_KEYS:
                try:
                    state[key] = default_val  # set even if missing, to seed defaults
                except Exception as val_err:
                    logger.debug("Failed to set default for key %s: %s", key, val_err)

        try:
            state_keys = list(state.keys()) if hasattr(state, "keys") else list(state)
        except Exception:
            state_keys = []

        for key in state_keys:
            if key in _PRESERVE_KEYS:
                continue

            is_orphan = False
            try:
                if isinstance(key, str):
                    if key in _ORPHAN_KEYS or any(key.startswith(p) for p in _ORPHAN_PREFIXES):
                        is_orphan = True
                elif key in _ORPHAN_KEYS:
                    is_orphan = True
            except Exception:
                pass

            if is_orphan:
                try:
                    state.pop(key, None)
                except Exception as pop_err:
                    logger.debug("Failed to pop key %s: %s", key, pop_err)

        # Re-arm the Human-in-the-Loop remediation gate. remediation_approved is an
        # orphan key (not a ReviewState field), so it's cleared via pop() above — but
        # ADK's session-state delta model does NOT reliably propagate a key DELETION
        # the way it propagates a SET. Setting it explicitly to False emits a
        # propagating delta that reliably re-arms the gate.
        try:
            state["remediation_approved"] = False
        except Exception as gate_err:
            logger.debug("Failed to reset remediation_approved: %s", gate_err)

        try:
            from agent_guardian.utils.loop_state import LoopState

            LoopState.clear(state)
        except Exception as loop_err:
            logger.debug("Failed to clear LoopState: %s", loop_err)

    except Exception as e:
        logger.error("reset_review_state failed (continuing with existing state): %s", e)
