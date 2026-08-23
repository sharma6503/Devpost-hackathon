"""Tests for planning_agent's deterministic fallback when its output is empty
or malformed. Without this fallback, downstream experts inherit corrupted
JSON in {review_plan} and may hallucinate assignments.
"""

from __future__ import annotations

from agent_guardian.sub_agents.planning_agent import _planning_after_callback


def _assert_fallback_plan(plan):
    assert isinstance(plan, dict)
    assert plan.get("strategy", "").startswith("FALLBACK")
    assignments = plan.get("assignments")
    assert isinstance(assignments, list) and assignments
    expert_names = {a["expert_name"] for a in assignments}
    assert {
        "quality_expert",
        "security_expert",
        "governance_expert",
        "adk_expert",
    }.issubset(expert_names)
    for a in assignments:
        assert a["assigned_modules"] == ["all"]


def test_planning_fallback_on_empty_output(mock_tool_context):
    mock_tool_context.state["review_plan"] = ""
    _planning_after_callback(mock_tool_context)
    _assert_fallback_plan(mock_tool_context.state["review_plan"])


def test_planning_fallback_on_malformed_json(mock_tool_context):
    mock_tool_context.state["review_plan"] = "this is not { valid json"
    _planning_after_callback(mock_tool_context)
    _assert_fallback_plan(mock_tool_context.state["review_plan"])


def test_planning_reassigns_unknown_modules_to_all(mock_tool_context):
    """Modules not present in module_map must be reassigned to ['all'] so
    experts do not 'review' modules that do not exist.
    """
    mock_tool_context.state["module_map"] = {"src/api": ["src/api/main.py"]}
    mock_tool_context.state["review_plan"] = {
        "is_large_codebase": True,
        "strategy": "Focused on src/api",
        "assignments": [
            {
                "expert_name": "quality_expert",
                "assigned_modules": ["src/api", "src/nonexistent"],
                "focus_areas": "x",
            },
            {
                "expert_name": "security_expert",
                "assigned_modules": ["src/ghost"],
                "focus_areas": "y",
            },
        ],
    }

    _planning_after_callback(mock_tool_context)

    plan = mock_tool_context.state["review_plan"]
    by_expert = {a["expert_name"]: a for a in plan["assignments"]}
    # Mixed valid+invalid -> reassigned to ['all']
    assert by_expert["quality_expert"]["assigned_modules"] == ["all"]
    # All-invalid -> reassigned to ['all']
    assert by_expert["security_expert"]["assigned_modules"] == ["all"]
