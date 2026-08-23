from __future__ import annotations

"""
agent_guardian/models/remediation.py

Pydantic schemas for the A2A remediation agent (Step 4 of upgrade plan).

These models define the structured output contract for the remediation_agent
that reads synthesis_result, maps findings to code changes, and opens
GitHub PRs via the GitHub MCP API.
"""

import re
from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator


def strip_code_fences(text: str | None) -> str | None:
    """Strip leading and trailing markdown code block fences if present in snippet fields."""
    if text is None:
        return None
    cleaned = str(text).strip()
    # Match ```language\n<code>\n``` or ```\n<code>\n```
    match = re.match(r"^```(?:[a-zA-Z0-9_\-]+)?\n?(.*?)\n?```$", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    return cleaned


class CodeChange(BaseModel):
    """A single file-level code change proposed by the remediation agent."""

    file_path: str = Field(description="Repository-relative path to the file to be changed (e.g. 'src/agent.py').")
    change_type: Literal["modify", "create", "delete"] = Field(description="Type of change to apply to the file.")
    original_snippet: str | None = Field(
        default=None,
        description=(
            "The exact original code block to be replaced. "
            "Required for change_type='modify'. Used for context in the PR diff."
        ),
    )
    replacement_snippet: str | None = Field(
        default=None,
        description=(
            "The replacement code block. Required for change_type='modify' or 'create'. "
            "Should be the complete, runnable replacement — not a diff."
        ),
    )
    finding_id: str = Field(
        description=(
            "Reference to the finding that motivated this change "
            "(e.g. 'SEC-003', 'QA-007'). Used in the PR description."
        ),
    )
    rationale: str = Field(
        description=(
            "1–2 sentence explanation of why this change addresses the finding. Included in the GitHub PR body."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def pre_validate_change(cls, data: Any) -> Any:
        """Coerce change type and strip markdown fences from code snippets."""
        if isinstance(data, dict):
            if "change_type" in data:
                ctype = str(data["change_type"]).lower().strip()
                if ctype in ("modify", "create", "delete"):
                    data["change_type"] = ctype
                else:
                    data["change_type"] = "modify"  # Default fallback
            else:
                data["change_type"] = "modify"

            if "original_snippet" in data:
                data["original_snippet"] = strip_code_fences(data["original_snippet"])
            if "replacement_snippet" in data:
                data["replacement_snippet"] = strip_code_fences(data["replacement_snippet"])

            if "finding_id" not in data or not data["finding_id"]:
                data["finding_id"] = "GEN-001"

            if "rationale" not in data or not data["rationale"]:
                data["rationale"] = "Automated mechanical fix implemented by Agent Guardian."
        return data


class RemediationPlan(BaseModel):
    """
    Structured output from the remediation_agent.

    Describes all proposed code changes, the target branch,
    and the PR metadata to be created via the GitHub MCP API.
    """

    target_repo: str = Field(description="GitHub repository in 'owner/repo' format (e.g. 'owner/my-agent').")
    base_branch: str = Field(
        default="main",
        description="The branch to open the PR against (e.g. 'main' or 'develop').",
    )
    pr_branch: str = Field(
        description=(
            "Name of the new branch to create for the remediation changes (e.g. 'guardian/remediation-2026-04-29')."
        ),
    )
    pr_title: str = Field(description="GitHub PR title summarising the remediation scope.")
    pr_body: str = Field(
        description=(
            "Full GitHub PR description in Markdown. Should include: "
            "1) Summary of findings addressed, 2) List of changed files, "
            "3) Agent Guardian report reference."
        ),
    )
    changes: list[CodeChange] = Field(description="Ordered list of file changes to apply before opening the PR.")
    priority: Literal["critical", "high", "medium", "low"] = Field(
        default="high",
        description="Overall priority of the remediation PR based on finding severities.",
    )
    estimated_risk: Literal["low", "medium", "high"] = Field(
        default="low",
        description=(
            "Estimated risk of applying these changes. Low = safe refactors. "
            "High = logic changes that require thorough review."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def pre_validate_plan(cls, data: Any) -> Any:
        """Coerce priority and estimated risk, defaulting missing metadata cleanly."""
        if isinstance(data, dict):
            if "priority" in data:
                prio = str(data["priority"]).lower().strip()
                if prio in ("critical", "high", "medium", "low"):
                    data["priority"] = prio
                else:
                    data["priority"] = "high"
            else:
                data["priority"] = "high"

            if "estimated_risk" in data:
                risk = str(data["estimated_risk"]).lower().strip()
                if risk in ("low", "medium", "high"):
                    data["estimated_risk"] = risk
                else:
                    data["estimated_risk"] = "low"
            else:
                data["estimated_risk"] = "low"

            if "changes" not in data or not data["changes"]:
                data["changes"] = []

            if "pr_branch" not in data or not data["pr_branch"]:
                data["pr_branch"] = "agent_guardian/remediation"

            if "pr_title" not in data or not data["pr_title"]:
                data["pr_title"] = "[Agent Guardian] Automated remediation changes"

            if "pr_body" not in data or not data["pr_body"]:
                data["pr_body"] = "Automated Pull Request submitted by Agent Guardian."
        return data
