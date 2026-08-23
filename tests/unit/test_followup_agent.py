from __future__ import annotations

"""Structural tests for the post-review follow-up Q&A agent.

These assert the wiring/safety contract without making live model calls:
- followup_agent is registered as a sub-agent of the root supervisor;
- it carries ONLY read-only tools (no branch/commit/PR/remediation writes);
- the transfer guards that prevent next-turn stickiness are set;
- the follow-up state fields exist and the prompt loads with the injection defense.
"""


WRITE_TOOL_MARKERS = ("create_branch", "create_or_update_file", "create_pull_request")


def _tool_names(agent):
    names = []
    for t in agent.tools:
        names.append(getattr(t, "__name__", getattr(t, "name", type(t).__name__)))
    return names


def test_followup_agent_registered_on_root():
    import agent_guardian.agent as a

    sub_names = [s.name for s in a.root_agent.sub_agents]
    assert "followup_agent" in sub_names
    assert "review_pipeline" in sub_names  # existing review path still present


def test_followup_agent_has_no_write_tools():
    from agent_guardian.sub_agents import followup_agent

    names = [n.lower() for n in _tool_names(followup_agent)]
    offending = [n for n in names if any(m in n for m in WRITE_TOOL_MARKERS)]
    assert offending == [], f"follow-up agent must be read-only, found: {offending}"


def test_followup_agent_transfer_guards_set():
    from agent_guardian.sub_agents import followup_agent

    # Both guards must be True so the supervisor re-routes every new turn
    # (otherwise a follow-up turn would hijack the next fresh-review request).
    assert followup_agent.disallow_transfer_to_parent is True
    assert followup_agent.disallow_transfer_to_peers is True
    assert followup_agent.output_key == "followup_answer"


def test_followup_state_fields_exist():
    from agent_guardian.state import ReviewState

    fields = ReviewState.model_fields
    assert "followup_question" in fields
    assert "followup_answer" in fields
    # Defaults are empty strings so they never accidentally read as a real review.
    s = ReviewState()
    assert s.followup_question == ""
    assert s.followup_answer == ""


def test_followup_prompt_loads_with_defense():
    from agent_guardian.prompts import FOLLOWUP_AGENT_PROMPT

    assert "{followup_question}" in FOLLOWUP_AGENT_PROMPT
    assert "{synthesis_result}" in FOLLOWUP_AGENT_PROMPT
    assert "PROMPT-INJECTION DEFENSE" in FOLLOWUP_AGENT_PROMPT
