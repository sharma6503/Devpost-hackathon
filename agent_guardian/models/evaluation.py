from __future__ import annotations

"""
agent_guardian/models/evaluation.py

Pydantic schemas for the evaluation_expert quality gate.

These models define the structured output contract between the
evaluation_expert agent and the LoopAgent orchestration layer.
"""

from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator
from ..sub_agents.registry import normalize_expert_name  # noqa: F401 — re-exported for compat


class ReviewScore(BaseModel):
    """Quality score for a single expert review across three dimensions."""

    agent: str = Field(description="Name of the agent being evaluated (e.g. 'quality_expert').")
    specificity: int = Field(
        ge=0,
        le=10,
        description=(
            "0–10: Does every finding cite an exact file:line reference? "
            "0 = no locations at all. 10 = every finding has file:line."
        ),
    )
    evidence: int = Field(
        ge=0,
        le=10,
        description=(
            "0–10: Are full Before/After code blocks provided? "
            "0 = no code shown. 10 = complete Before/After for every finding."
        ),
    )
    actionability: int = Field(
        ge=0,
        le=10,
        description=(
            "0–10: Are remediations copy-paste-ready? 0 = vague 'fix this'. 10 = complete, runnable fix instructions."
        ),
    )
    avg: float = Field(description="Average of specificity, evidence, and actionability scores.")

    @model_validator(mode="before")
    @classmethod
    def pre_validate_score(cls, data: Any) -> Any:
        """Normalize, clamp, and compute fields to guarantee structured correctness."""
        if isinstance(data, dict):
            # Normalize agent name
            if "agent" in data:
                data["agent"] = normalize_expert_name(data["agent"])

            # Coerce scores to int and clamp to [0, 10]
            for field in ("specificity", "evidence", "actionability"):
                if field in data:
                    try:
                        val = int(float(data[field]))
                        data[field] = max(0, min(10, val))
                    except (ValueError, TypeError):
                        data[field] = 0
                else:
                    data[field] = 0

            # Recompute avg to be perfectly correct
            spec = data.get("specificity", 0)
            ev = data.get("evidence", 0)
            act = data.get("actionability", 0)
            data["avg"] = round((spec + ev + act) / 3, 2)
        return data


class EvaluationResult(BaseModel):
    """
    Structured output from the evaluation_expert agent.

    The LoopAgent reads `remediation_required` via state to decide
    whether to continue iterating or exit the quality gate.
    """

    scores: list[ReviewScore] = Field(description="Per-agent quality scores across all three dimensions.")
    overall_grade: Literal["PASS", "FAIL"] = Field(
        description=(
            "PASS if ALL agents meet the configured eval_pass_threshold on ALL dimensions. "
            "FAIL if any agent is below threshold on any dimension."
        ),
    )
    weakest_agent: str | None = Field(
        default=None,
        description=(
            "Name of the agent with the lowest average score, or null if all pass. "
            "Used by revision_agent to target the correct review for rewriting."
        ),
    )
    weakest_dimension: str | None = Field(
        default=None,
        description=(
            "The dimension (specificity | evidence | actionability) where the "
            "weakest agent scored lowest. Guides the revision prompt."
        ),
    )
    remediation_required: bool = Field(
        description=(
            "True = LoopAgent should continue; False = output is ready for synthesis. "
            "Set to False when overall_grade is PASS."
        ),
    )
    feedback: str = Field(
        description=(
            "2–3 sentence actionable feedback for the weakest agent. "
            "Should specify exactly what is missing and how to improve."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def pre_validate_result(cls, data: Any) -> Any:
        """Coerce grades, dimensions, agent names, and boolean requirements gracefully."""
        if isinstance(data, dict):
            # Normalize grade to uppercase Literal
            grade = str(data.get("overall_grade", "")).upper().strip()
            data["overall_grade"] = "PASS" if "PASS" in grade else "FAIL"

            # Normalize weakest_agent name
            if "weakest_agent" in data and data["weakest_agent"]:
                if str(data["weakest_agent"]).lower().strip() == "null":
                    data["weakest_agent"] = None
                else:
                    data["weakest_agent"] = normalize_expert_name(data["weakest_agent"])

            # Normalize weakest_dimension
            if "weakest_dimension" in data and data["weakest_dimension"]:
                dim = str(data["weakest_dimension"]).lower().strip()
                if dim == "null":
                    data["weakest_dimension"] = None
                elif "specificity" in dim:
                    data["weakest_dimension"] = "specificity"
                elif "evidence" in dim:
                    data["weakest_dimension"] = "evidence"
                elif "actionability" in dim:
                    data["weakest_dimension"] = "actionability"
                else:
                    data["weakest_dimension"] = None

            # Coerce boolean remediation_required
            if "remediation_required" in data:
                val = data["remediation_required"]
                if isinstance(val, str):
                    data["remediation_required"] = val.lower().strip() == "true"
                else:
                    data["remediation_required"] = bool(val)
            else:
                # Deduce from grade if missing
                grade = data.get("overall_grade", "FAIL")
                data["remediation_required"] = grade == "FAIL"

            # Fallback for feedback if missing
            if "feedback" not in data or not data["feedback"]:
                data["feedback"] = (
                    "Expert review meets minimum criteria."
                    if data.get("overall_grade") == "PASS"
                    else "Review requires refinement of specificity, evidence, and actionable items."
                )
        return data
