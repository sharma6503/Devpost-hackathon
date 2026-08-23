from __future__ import annotations

"""
Markdown Structurizers for Agent Guardian.

Converts structured JSON data / Pydantic models from pipeline agents
into clean, well-formatted, human-readable Markdown representations.
"""

from typing import Any, Dict


def format_review_plan_md(plan_data: Dict[str, Any] | Any) -> str:
    """Format ReviewPlan dict or model into readable Markdown."""
    if hasattr(plan_data, "model_dump"):
        data = plan_data.model_dump()
    elif isinstance(plan_data, dict):
        data = plan_data
    else:
        return str(plan_data)

    is_large = data.get("is_large_codebase", False)
    strategy = data.get("strategy", "Standard full review")
    assignments = data.get("assignments", [])

    lines = [
        "### 📋 Codebase Review & Division Strategy",
        f"- **Codebase Scope:** {'Large Codebase (Targeted Module Division)' if is_large else 'Standard Codebase (Full Coverage)'}",
        f"- **Strategy:** {strategy}\n",
        "#### 🤖 Specialist Assignments",
    ]

    for assign in assignments:
        if isinstance(assign, dict):
            name = assign.get("expert_name", "expert")
            mods = assign.get("assigned_modules", ["all"])
            focus = assign.get("focus_areas", "General review")
        else:
            name = getattr(assign, "expert_name", "expert")
            mods = getattr(assign, "assigned_modules", ["all"])
            focus = getattr(assign, "focus_areas", "General review")

        mods_str = ", ".join(f"`{m}`" for m in mods) if isinstance(mods, list) else f"`{mods}`"
        title = str(name).replace("_", " ").title()
        lines.append(f"1. **`{title}`**")
        lines.append(f"   - **Assigned Modules:** {mods_str}")
        lines.append(f"   - **Focus Areas:** {focus}")

    return "\n".join(lines)


def format_metrics_md(metrics_data: Dict[str, Any] | Any) -> str:
    """Format MetricsSummary dict or model into readable Markdown."""
    if hasattr(metrics_data, "model_dump"):
        data = metrics_data.model_dump()
    elif isinstance(metrics_data, dict):
        data = metrics_data
    else:
        return str(metrics_data)

    total = data.get("total", 0)
    severity = data.get("severity", {}) or {}
    scores = data.get("scores", {}) or {}
    category = data.get("category", {}) or {}

    overall_score = scores.get("overall", 0)
    crit = severity.get("critical", 0)
    high = severity.get("high", 0)
    med = severity.get("medium", 0)
    low = severity.get("low", 0)

    lines = [
        "### 📊 Codebase Health & Metrics Summary",
        f"- **Overall Health Score:** `{overall_score}/100`",
        f"- **Total Identified Findings:** `{total}`",
        "\n#### 🚨 Severity Distribution",
        f"- 🔴 **Critical:** `{crit}`",
        f"- 🟠 **High:** `{high}`",
        f"- 🟡 **Medium:** `{med}`",
        f"- 🟢 **Low:** `{low}`",
    ]

    if category:
        lines.append("\n#### 🏷️ Findings by Category")
        for cat, count in category.items():
            lines.append(f"- **{cat.replace('_', ' ').title()}:** `{count}`")

    if scores:
        lines.append("\n#### 📐 Domain Health Scores")
        for domain, score in scores.items():
            if domain != "overall":
                lines.append(f"- **{domain.replace('_', ' ').title()}:** `{score}/100`")

    return "\n".join(lines)


def format_evaluation_md(eval_data: Dict[str, Any] | Any) -> str:
    """Format EvaluationResult dict or model into readable Markdown."""
    if hasattr(eval_data, "model_dump"):
        data = eval_data.model_dump()
    elif isinstance(eval_data, dict):
        data = eval_data
    else:
        return str(eval_data)

    grade = data.get("overall_grade", "N/A")
    remediation_req = data.get("remediation_required", False)
    weakest = data.get("weakest_agent", "")
    feedback = data.get("feedback", "")
    dimension_scores = data.get("dimension_scores", {}) or {}

    passed = not remediation_req
    status_icon = "✅" if passed else "⚠️"
    status_text = "PASSED (Quality Threshold Met)" if passed else "REVISION REQUIRED"

    lines = [
        f"### {status_icon} Quality Gate Verification",
        f"- **Evaluation Grade:** `{grade}`",
        f"- **Status:** {status_text}",
    ]

    if dimension_scores:
        lines.append("\n#### 📏 Review Quality Dimensions")
        for dim, score in dimension_scores.items():
            lines.append(f"- **{dim.replace('_', ' ').title()}:** `{score}/100`")

    if not passed:
        if weakest:
            lines.append(f"- **Weakest Review Expert:** `{weakest}`")
        if feedback:
            lines.append(f"\n#### 💡 Self-Correction Feedback\n{feedback}")

    return "\n".join(lines)


def format_remediation_plan_md(plan_data: Dict[str, Any] | Any) -> str:
    """Format RemediationPlan dict or model into readable Markdown."""
    if hasattr(plan_data, "model_dump"):
        data = plan_data.model_dump()
    elif isinstance(plan_data, dict):
        data = plan_data
    else:
        return str(plan_data)

    pr_title = data.get("pr_title", "Automated Remediation PR")
    target_repo = data.get("target_repo", "N/A")
    pr_branch = data.get("pr_branch", "N/A")
    base_branch = data.get("base_branch", "main")
    priority = data.get("priority", "medium")
    risk = data.get("estimated_risk", "low")
    changes = data.get("changes", [])

    lines = [
        "### 🛠️ Proposed Remediation Plan",
        f"- **PR Title:** {pr_title}",
        f"- **Target Repository:** `{target_repo}`",
        f"- **Branches:** `{pr_branch}` → `{base_branch}`",
        f"- **Priority:** `{str(priority).upper()}` | **Estimated Risk:** `{str(risk).upper()}`",
        f"\n#### 📝 Proposed File Changes ({len(changes)})",
    ]

    for idx, change in enumerate(changes, 1):
        if isinstance(change, dict):
            ctype = change.get("change_type", "modify")
            fpath = change.get("file_path", "")
            rationale = change.get("rationale", "")
            finding_id = change.get("finding_id", "")
        else:
            ctype = getattr(change, "change_type", "modify")
            fpath = getattr(change, "file_path", "")
            rationale = getattr(change, "rationale", "")
            finding_id = getattr(change, "finding_id", "")

        lines.append(f"{idx}. **`[{str(ctype).upper()}]`** `{fpath}`")
        if finding_id:
            lines.append(f"   - **Finding Ref:** `{finding_id}`")
        lines.append(f"   - **Rationale:** {rationale}")

    return "\n".join(lines)
