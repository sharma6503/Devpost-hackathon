from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, model_validator
from ..sub_agents.registry import normalize_expert_name


class ExpertAssignment(BaseModel):
    expert_name: str = Field(description="Name of the expert agent (e.g. 'quality_expert', 'security_expert').")
    assigned_modules: list[str] = Field(
        description="List of specific modules (from module_map) assigned to this expert."
    )
    focus_areas: str = Field(description="Instructions or focus areas for the expert in these modules.")

    @model_validator(mode="before")
    @classmethod
    def pre_validate_assignment(cls, data: Any) -> Any:
        """Coerce strings to lists for modules and normalize expert names."""
        if isinstance(data, dict):
            if "expert_name" in data:
                data["expert_name"] = normalize_expert_name(data["expert_name"])

            if "assigned_modules" in data:
                modules = data["assigned_modules"]
                if isinstance(modules, str):
                    data["assigned_modules"] = [modules]
                elif isinstance(modules, list):
                    data["assigned_modules"] = [str(m) for m in modules]
                else:
                    data["assigned_modules"] = ["all"]
            else:
                data["assigned_modules"] = ["all"]

            if "focus_areas" not in data or not data["focus_areas"]:
                data["focus_areas"] = "Audit the assigned codebase components."
        return data


class ReviewPlan(BaseModel):
    """
    Structured plan for the review fleet, detailing which expert reviews which modules.
    This prevents context saturation in large codebases.
    """

    is_large_codebase: bool = Field(
        description="Whether the codebase was deemed large enough to require strict module assignment."
    )
    strategy: str = Field(
        description="Overall strategy for the review (e.g. 'Focused on core business logic, skipping UI')."
    )
    assignments: list[ExpertAssignment] = Field(description="Assignments for each expert agent.")

    @model_validator(mode="before")
    @classmethod
    def pre_validate_plan(cls, data: Any) -> Any:
        """Coerce boolean settings and provide fallback empty lists/default strings."""
        if isinstance(data, dict):
            if "is_large_codebase" in data:
                val = data["is_large_codebase"]
                if isinstance(val, str):
                    data["is_large_codebase"] = val.lower().strip() == "true"
                else:
                    data["is_large_codebase"] = bool(val)
            else:
                data["is_large_codebase"] = False

            if "strategy" not in data or not data["strategy"]:
                data["strategy"] = "Focused analysis on all modules."

            if "assignments" not in data or not data["assignments"]:
                data["assignments"] = []
        return data
