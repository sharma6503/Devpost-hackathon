"""Unit tests for agent_guardian.utils.markdown_format functions."""

from agent_guardian.models.evaluation import EvaluationResult, ReviewScore
from agent_guardian.models.planning import ExpertAssignment, ReviewPlan
from agent_guardian.models.remediation import CodeChange, RemediationPlan
from agent_guardian.utils.markdown_format import (
    format_evaluation_md,
    format_metrics_md,
    format_remediation_plan_md,
    format_review_plan_md,
)


def test_format_review_plan_md():
    assignment = ExpertAssignment(
        expert_name="quality_expert",
        assigned_modules=["core", "utils"],
        focus_areas="Focus on error handling and type hints.",
    )
    plan = ReviewPlan(
        is_large_codebase=False,
        strategy="Comprehensive codebase review focusing on core modules.",
        assignments=[assignment],
    )

    md = format_review_plan_md(plan)
    assert "### 📋 Codebase Review & Division Strategy" in md
    assert "Quality Expert" in md
    assert "core" in md
    assert "Focus on error handling" in md


def test_format_metrics_md():
    metrics_data = {
        "total": 10,
        "severity": {"critical": 2, "high": 5, "medium": 3, "low": 0},
        "scores": {"overall": 88},
        "category": {"security": 2, "quality": 8},
    }

    md = format_metrics_md(metrics_data)
    assert "### 📊 Codebase Health & Metrics Summary" in md
    assert "88/100" in md
    assert "Total Identified Findings:** `10`" in md
    assert "Critical:** `2`" in md


def test_format_evaluation_md():
    score = ReviewScore(
        agent="quality_expert",
        specificity=9,
        evidence=8,
        actionability=10,
    )
    result = EvaluationResult(
        scores=[score],
        overall_grade="PASS",
        weakest_agent=None,
        weakest_dimension=None,
        remediation_required=False,
        feedback="All expert reviews meet quality criteria.",
    )

    md = format_evaluation_md(result)
    assert "### ✅ Quality Gate Verification" in md
    assert "PASS" in md
    assert "PASSED (Quality Threshold Met)" in md


def test_format_remediation_plan_md():
    change = CodeChange(
        file_path="config.py",
        change_type="modify",
        original_snippet="model = 'gemini-flash'",
        replacement_snippet="model = 'gemini-2.5-flash'",
        finding_id="GOV-01",
        rationale="Pin model version to compliant release.",
    )
    plan = RemediationPlan(
        target_repo="imonline/agent-guardian",
        base_branch="main",
        pr_branch="fix/gov-01",
        pr_title="[Agent Guardian] Pin model version",
        pr_body="Fix model version pinning and credentials leak.",
        changes=[change],
        priority="high",
        estimated_risk="low",
    )

    md = format_remediation_plan_md(plan)
    assert "### 🛠️ Proposed Remediation Plan" in md
    assert "HIGH" in md
    assert "config.py" in md
    assert "GOV-01" in md
    assert "Pin model version to compliant release." in md
