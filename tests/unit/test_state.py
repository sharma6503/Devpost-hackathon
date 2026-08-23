from agent_guardian.state import ReviewState, reset_review_state


def test_review_state_initialization():
    """Verify that ReviewState initializes with correct default values."""
    state = ReviewState()
    assert state.user_request == ""
    assert state.is_large_codebase is False
    assert state.logic_file_count == 0
    assert state.constitution == "Be professional and concise."
    assert "CONFLUENCE_UNAVAILABLE" in state.confluence_rules
    assert state.governance_review_result == "Not provided or skipped."


def test_review_state_mutation():
    """Verify that state fields can be updated correctly."""
    state = ReviewState()
    state.user_request = "Audit this repo"
    state.total_file_count = 10
    state.is_large_codebase = True

    assert state.user_request == "Audit this repo"
    assert state.total_file_count == 10
    assert state.is_large_codebase is True


def test_review_state_complex_types():
    """Verify that complex nested types work as expected."""
    state = ReviewState()

    # Mock ReviewPlan
    mock_plan = {"plan": "some plan"}
    state.review_plan = mock_plan
    assert state.review_plan == mock_plan

    # Mock module_map
    state.module_map = {"main.py": {"imports": ["os"]}}
    assert state.module_map["main.py"]["imports"] == ["os"]


def test_review_state_serialization():
    """Verify that ReviewState can be serialized to a dictionary."""
    state = ReviewState(user_request="test")
    dump = state.model_dump()
    assert dump["user_request"] == "test"
    assert "constitution" in dump
    assert dump["logic_file_count"] == 0


def test_reset_review_state_purges_remediation_source_context():
    """A prior review's prefetched source snippets must not bleed into the next
    review's remediation-planner prompt."""
    state = {"remediation_source_context": "stale content from a prior review"}
    reset_review_state(state)
    assert "remediation_source_context" not in state


def test_reset_review_state_rearms_remediation_approved():
    """remediation_approved must be explicitly reset to False (not just popped),
    since ADK's state-delta model doesn't reliably propagate key deletion."""
    state = {"remediation_approved": True}
    reset_review_state(state)
    assert state["remediation_approved"] is False
