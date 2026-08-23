from __future__ import annotations
import json
import pytest
from agent_guardian.sub_agents.remediation_agent import _planner_after_callback
from agent_guardian.tools.governance_tools import scan_governance


def test_remediation_branch_naming(mock_tool_context):
    """Verifies that the remediation agent uses the correct 'agent_guardian/review' branch name."""
    # Mock planning result
    mock_tool_context.state["remediation_plan"] = {
        "target_repo": "owner/repo",
        "changes": [],
        "pr_title": "Fixes",
        "pr_body": "Body",
        "priority": "high",
        "estimated_risk": "low",
    }

    # Run callback
    _planner_after_callback(mock_tool_context)

    # Verify the branch name was injected
    plan_json = mock_tool_context.state["remediation_plan"]
    plan = json.loads(plan_json)
    assert plan["pr_branch"] == "agent_guardian/review"


def test_scan_governance_concatenated_blocks():
    """Verifies that scan_governance correctly splits and scans concatenated codebase blocks."""
    concatenated_content = """--- main.py ---
import requests
def run():
    requests.get("https://google.com") # Missing timeout

--- utils.py ---
API_KEY = "AIzaSySecret" # Hardcoded secret
"""

    # Test AST check on concatenated block
    # Previously this would cause a SyntaxError
    result_str = scan_governance("combined", concatenated_content, "ast_check")
    result = json.loads(result_str)

    # Verify we got findings from both "files"
    files_with_issues = [r["file"] for r in result]
    assert "main.py" in files_with_issues
    assert any("REL-001" in r["issue"] for r in result if r["file"] == "main.py")

    # Test Regex scan on concatenated block
    result_str_regex = scan_governance("combined", concatenated_content, "regex_scan")
    result_regex = json.loads(result_str_regex)
    assert any("AIzaSySecret" in r["match"] for r in result_regex if r["file"] == "utils.py")


def test_remediation_repo_injection(mock_tool_context):
    """Verifies that the remediation planner uses the default repo from environment if missing."""
    import os

    # Set the environment variable that Config() reads
    os.environ["GITHUB_REMEDIATION_REPO"] = "enterprise-org/fallback-repo"

    # Plan missing target_repo
    mock_tool_context.state["remediation_plan"] = {
        "changes": [],
        "pr_branch": "agent_guardian/review",
        "pr_title": "Fixes",
        "pr_body": "Body",
        "priority": "high",
        "estimated_risk": "low",
    }

    _planner_after_callback(mock_tool_context)

    # Callback should have converted it to a JSON string
    plan_data = mock_tool_context.state["remediation_plan"]
    assert isinstance(plan_data, str)

    plan = json.loads(plan_data)
    assert plan["target_repo"] == "enterprise-org/fallback-repo"
    assert plan["pr_branch"] == "agent_guardian/review"


@pytest.mark.asyncio
async def test_remediation_agent_skip_routing():
    """Verify that remediation_agent handles the 'skip' route from remediation_gate without hanging/failing."""
    import os
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from agent_guardian.sub_agents.remediation_agent import remediation_agent
    from agent_guardian.agent import WorkflowAgent
    from google.genai import types as genai_types

    # Prevent test pollution from previous test
    old_repo = os.environ.pop("GITHUB_REMEDIATION_REPO", None)

    try:
        session_service = InMemorySessionService()
        user_id = "test_user"
        session_id = "test_session"
        await session_service.create_session(app_name="agent_guardian", user_id=user_id, session_id=session_id)

        session = await session_service.get_session(app_name="agent_guardian", user_id=user_id, session_id=session_id)
        session.state["user_request"] = "local review with no repo"
        session.state["synthesis_result"] = "Synthesis findings"

        # Wrap remediation_agent in WorkflowAgent so Runner can run it
        wrapped_agent = WorkflowAgent(name="remediation_agent", workflow=remediation_agent)

        runner = Runner(
            agent=wrapped_agent,
            app_name="agent_guardian",
            session_service=session_service,
        )

        # Run the agent
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text="")]),
        ):
            events.append(event)

        # Verify that the workflow successfully terminates and returns skip
        assert any("Remediation skipped" in (getattr(e, "output", "") or "") for e in events)
    finally:
        if old_repo is not None:
            os.environ["GITHUB_REMEDIATION_REPO"] = old_repo
