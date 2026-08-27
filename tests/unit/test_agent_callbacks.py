import pytest
import os
import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from agent_guardian.agent import (
    constitution_callback,
    pacing_callback,
)
from agent_guardian.state import reset_review_state


@pytest.fixture
def mock_callback_context():
    context = MagicMock()
    context.state = {}
    context.agent_name = "test_agent"
    return context


@pytest.mark.asyncio
async def test_constitution_callback(mock_callback_context):
    """Verify that constitution_callback initializes the state with default values."""
    with patch("agent_guardian.utils.callbacks.os.path.exists", return_value=False):
        await constitution_callback(mock_callback_context)

    assert "constitution" in mock_callback_context.state
    assert "today" in mock_callback_context.state
    assert mock_callback_context.state["today"] == datetime.date.today().strftime("%Y-%m-%d")
    assert "confluence_rules" in mock_callback_context.state
    assert "confluence_host_map_json" in mock_callback_context.state


_AUTHORIZED_REPO_CASES = [
    # (url in user_request, expected authorized_github_repo)
    ("Review https://github.com/acme/toolkit", "toolkit"),
    ("Review https://github.com/acme/toolkit.git", "toolkit"),
    # Names ending in chars that str.rstrip(".git") would wrongly strip.
    ("Audit https://github.com/acme/api", "api"),
    ("Audit https://github.com/acme/logging", "logging"),
]


@pytest.mark.parametrize("user_request,expected_repo", _AUTHORIZED_REPO_CASES)
@pytest.mark.asyncio
async def test_constitution_callback_authorizes_full_repo_name(mock_callback_context, user_request, expected_repo):
    """The GitHub repo is extracted by suffix-strip, not char-strip.

    Regression for `.rstrip(".git")`, which strips any trailing '.','g','i','t'
    (e.g. 'toolkit' -> 'toolk'). Must only drop a literal '.git' suffix.
    """
    mock_callback_context.state["user_request"] = user_request
    # Skip file interception so it doesn't overwrite the pre-set user_request.
    mock_callback_context.user_content = None
    mock_callback_context.session = None

    with patch("agent_guardian.utils.callbacks.os.path.exists", return_value=False):
        await constitution_callback(mock_callback_context)

    assert mock_callback_context.state["authorized_github_owner"] == "acme"
    assert mock_callback_context.state["authorized_github_repo"] == expected_repo


@pytest.mark.asyncio
async def test_pacing_callback_no_delay(mock_callback_context):
    """Verify that pacing_callback works without delay when no 429s occurred."""
    mock_callback_context.state["temp:429_retry_count"] = 0

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with patch.dict(os.environ, {"PACING_FORCE_DELAY_SEC": "0"}):
            await pacing_callback(mock_callback_context)
            mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_pacing_callback_with_retries(mock_callback_context):
    """Verify that pacing_callback introduces delay when 429 retries exist."""
    mock_callback_context.state["temp:429_retry_count"] = 1  # First retry

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with patch.dict(os.environ, {"PACING_DELAY_SEC": "10"}):
            await pacing_callback(mock_callback_context)
            # delay = base_delay * (2 ** retry_count) = 10 * 2 = 20
            mock_sleep.assert_called_once_with(20)


def test_reset_review_state_purges_stale_and_orphan_keys():
    """reset_review_state restores defaults, drops orphan/loop keys, keeps the request."""
    state = {
        "user_request": "Review repo X",
        "_previous_user_request": "Review repo X",
        "governance_review_result": "Old Result",
        "total_file_count": 50,
        "evaluation_grade": "FAIL",
        # Turn-scoped upload signal, owned by constitution_callback (set/cleared
        # from live user_content BEFORE reset runs). Reset must NOT purge it, or a
        # freshly uploaded ZIP would be wiped before ingestion reads it.
        "uploaded_zip_path": "/tmp/foo.zip",
        # Run-scoped orphans that are NOT ReviewState fields:
        "temp:429_retry_count": 3,
        "confluence_page_123": "stale page body",
        # Quality-gate loop carried over from a prior review:
        "temp:quality_gate": {"iterations": 2, "parse_failures": 3},
    }

    reset_review_state(state)

    # Defined fields reset to their ReviewState defaults
    assert state["governance_review_result"] == "Not provided or skipped."
    assert state["total_file_count"] == 0
    assert state["evaluation_grade"] == "Not provided or skipped."
    # Turn-scoped upload signal is PRESERVED (constitution_callback owns it)
    assert state["uploaded_zip_path"] == "/tmp/foo.zip"
    # Orphan keys removed entirely
    assert "temp:429_retry_count" not in state
    assert "confluence_page_123" not in state
    # Loop record cleared
    assert "temp:quality_gate" not in state
    # Request identity preserved
    assert state["user_request"] == "Review repo X"


def test_reset_review_state_is_unconditional():
    """Reset happens every call — even when the request is unchanged (re-run case)."""
    state = {
        "user_request": "Same Request",
        "_previous_user_request": "Same Request",
        "governance_review_result": "Stale Result",
    }

    reset_review_state(state)

    assert state["governance_review_result"] == "Not provided or skipped."


def test_reset_review_state_resilience_to_non_string_keys():
    """Verify reset_review_state does not raise errors on integer, float, or None keys."""
    state = {
        0: "integer_key_value",
        3.14: "float_key_value",
        None: "none_key_value",
        "user_request": "Same Request",
        "_previous_user_request": "Same Request",
        "governance_review_result": "Stale Result",
    }

    # Should run to completion without raising AttributeError or KeyError
    reset_review_state(state)

    assert state["governance_review_result"] == "Not provided or skipped."
    assert state[0] == "integer_key_value"
    assert state[3.14] == "float_key_value"
    assert state[None] == "none_key_value"


def test_loop_state_clear():
    """LoopState.clear drops the loop record so the next review starts fresh."""
    from agent_guardian.utils.loop_state import LoopState

    state = {"temp:quality_gate": {"iterations": 2, "parse_failures": 1}}
    LoopState.clear(state)
    assert "temp:quality_gate" not in state
    # A subsequent read returns a pristine loop.
    loop = LoopState.read(state)
    assert loop.iterations == 0
    assert loop.parse_failures == 0


def test_safe_mcp_toolset_invalidate():
    """invalidate() drops cached discovery so the next get_tools re-discovers."""
    from agent_guardian.utils import compat
    from agent_guardian.utils.compat import SafeMcpToolset

    if not getattr(compat, "_ADK_AVAILABLE", False):
        pytest.skip("ADK unavailable — SafeMcpToolset is the no-op stub")

    ts = SafeMcpToolset.__new__(SafeMcpToolset)
    # Simulate a prior successful discovery.
    ts._discovered_tools = ["cached_tool"]
    ts.last_error = "some prior error"

    ts.invalidate()

    assert ts._discovered_tools is None
    assert ts.last_error is None


def test_invalidate_all_safe_toolsets_sweeps_registry():
    """The module-level sweep re-arms every live toolset and never raises."""
    from agent_guardian.utils import compat
    from agent_guardian.utils.compat import (
        SafeMcpToolset,
        invalidate_all_safe_toolsets,
        _ALL_TOOLSETS,
    )

    if not getattr(compat, "_ADK_AVAILABLE", False):
        pytest.skip("ADK unavailable — SafeMcpToolset is the no-op stub")

    ts = SafeMcpToolset.__new__(SafeMcpToolset)
    ts._discovered_tools = ["cached_tool"]
    ts.last_error = None
    _ALL_TOOLSETS.add(ts)

    invalidate_all_safe_toolsets()

    assert ts._discovered_tools is None


# ---------------------------------------------------------------------------
# 5A — Evaluation loop infinite-loop guard
# ---------------------------------------------------------------------------


def test_eval_loop_guard_forces_exit_after_3_failures(mock_callback_context):
    """Three consecutive malformed JSON outputs must force LoopAgent exit on the third call."""
    from agent_guardian.sub_agents.evaluation_expert import _evaluation_after_callback
    from agent_guardian.utils.loop_state import LoopState

    mock_callback_context.state["evaluation_result"] = "NOT VALID JSON {{{"

    # First two failures must NOT force exit
    for i in range(1, 3):
        _evaluation_after_callback(mock_callback_context)
        loop = LoopState.read(mock_callback_context.state)
        assert loop.exit_requested is not True, f"Loop must not exit after failure #{i}"
        assert loop.parse_failures == i

    # Third failure MUST force exit
    _evaluation_after_callback(mock_callback_context)
    loop = LoopState.read(mock_callback_context.state)
    assert loop.exit_requested is True
    assert mock_callback_context.state["evaluation_grade"] == "FORCE_EXIT"


# ---------------------------------------------------------------------------
# 5B — Revision agent silent output-loss guard
# ---------------------------------------------------------------------------


def test_revision_guard_forces_exit_on_empty_target_key(mock_callback_context):
    """Empty failing_review_key must immediately force loop exit to prevent infinite spin."""
    from agent_guardian.sub_agents.revision_agent import _persist_revised_review
    from agent_guardian.utils.loop_state import LoopState

    mock_callback_context.state["failing_review_key"] = ""
    mock_callback_context.state["revised_review_content"] = "Some improved review text"

    _persist_revised_review(mock_callback_context)

    assert LoopState.read(mock_callback_context.state).exit_requested is True


def test_revision_persists_review_to_correct_key(mock_callback_context):
    """Revised content is written to the correct state key when failing_review_key is set."""
    from agent_guardian.sub_agents.revision_agent import _persist_revised_review
    from agent_guardian.utils.loop_state import LoopState

    mock_callback_context.state["failing_review_key"] = "quality_review_result"
    mock_callback_context.state["revised_review_content"] = "Improved quality review"

    _persist_revised_review(mock_callback_context)

    assert mock_callback_context.state["quality_review_result"] == "Improved quality review"
    assert LoopState.read(mock_callback_context.state).exit_requested is not True


# ---------------------------------------------------------------------------
# 5C — save_html_report_callback template-load failure propagation
# ---------------------------------------------------------------------------

_HTML_AGENT_STATE = {
    "html_report_content": "[TITLE]: Test Report\n[SUMMARY]: Summary.\n[CONTENT]: Content.",
    "governance_review_result": "APPROVED: all gates pass",
    "metrics_json": "{}",
    "remediation_html": "",
    "expert_reviews_html": "",
    "repo_metadata_html": "",
    "metrics_chart_html": "",
    "scorecard_html": "",
    "overall_score": "0",
    "report_grade": "U",
    "confidence_score": "0.0",
    "current_date": "January 01, 2026",
}


@pytest.mark.asyncio
async def test_save_html_report_callback_template_failure(mock_callback_context):
    """Template load failure writes error HTML to state instead of silently returning None."""
    from agent_guardian.sub_agents.html_agent import save_html_report_callback
    from unittest.mock import AsyncMock, patch

    mock_callback_context.state.update(_HTML_AGENT_STATE)
    mock_callback_context.save_artifact = AsyncMock()

    with patch(
        "agent_guardian.sub_agents.html_agent.structurize_findings_html",
        return_value="",
    ):
        with patch(
            "agent_guardian.sub_agents.html_agent.structurize_governance_md",
            return_value="",
        ):
            with patch(
                "builtins.open",
                side_effect=FileNotFoundError("template.html not found"),
            ):
                await save_html_report_callback(mock_callback_context)

    result = mock_callback_context.state.get("html_report_content", "")
    assert "Report generation failed" in result
    assert "template.html not found" in result
    mock_callback_context.save_artifact.assert_not_called()


# ---------------------------------------------------------------------------
# 5D — STATUS_DISPLAY triple-state parametrized test
# ---------------------------------------------------------------------------

_STATUS_DISPLAY_CASES = [
    ("REJECTED: hard gate failure SEC-001", "REJECTED"),
    ("APPROVED WITH CONDITIONS: soft-gate warnings present", "CONDITIONAL"),
    ("APPROVED: full compliance confirmed", "CERTIFIED"),
]


@pytest.mark.parametrize("gov_text,expected_label", _STATUS_DISPLAY_CASES)
@pytest.mark.asyncio
async def test_status_display_triple_state(mock_callback_context, gov_text, expected_label):
    """STATUS_DISPLAY badge must reflect the three governance verdict states correctly."""
    from agent_guardian.sub_agents.html_agent import save_html_report_callback
    from unittest.mock import AsyncMock, patch, MagicMock

    state = dict(_HTML_AGENT_STATE)
    state["governance_review_result"] = gov_text
    mock_callback_context.state.update(state)
    mock_callback_context.save_artifact = AsyncMock()

    def _open_side_effect(file, mode="r", **kwargs):
        if "b" in mode:
            # Image file — raise so _img() returns the SVG placeholder
            raise FileNotFoundError()
        # Template file — serve a minimal template with only the placeholder under test
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value="{{STATUS_DISPLAY}}")))
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    with patch(
        "agent_guardian.sub_agents.html_agent.structurize_findings_html",
        return_value="",
    ):
        with patch(
            "agent_guardian.sub_agents.html_agent.structurize_governance_md",
            return_value="",
        ):
            with patch("builtins.open", side_effect=_open_side_effect):
                await save_html_report_callback(mock_callback_context)

    result = mock_callback_context.state.get("html_report_content", "")
    assert expected_label in result, (
        f"Expected '{expected_label}' in STATUS_DISPLAY for gov_text={gov_text!r}.\nGot: {result[:400]}"
    )


# ---------------------------------------------------------------------------
# 6 — block_github_wrong_repo: hallucinated-repo guard on empty authorization
# ---------------------------------------------------------------------------


def _guard_ctx(state):
    ctx = MagicMock()
    ctx.state = state
    return ctx


def _guard_tool(name):
    tool = MagicMock()
    tool.name = name
    return tool


def test_guard_blocks_hallucinated_repo_when_unauthorized():
    """Empty authorized fields + a repo-scoped fetch to a guessed repo is blocked.

    Reproduces the follow-up hallucination where the agent fetches google/adk-python
    after a ZIP/inline review that never set an authorized repo.
    """
    from agent_guardian.utils.tool_guards import block_github_wrong_repo

    result = block_github_wrong_repo(
        _guard_tool("github_get_file_contents"),
        {"owner": "google", "repo": "adk-python", "path": "src/agent.py"},
        _guard_ctx({"authorized_github_owner": "", "authorized_github_repo": ""}),
    )

    assert result is not None
    assert result["error"] == "NO_AUTHORIZED_REPO"


def test_guard_blocks_search_when_unauthorized():
    """Search tools bypass owner/repo scoping — blocked even with no authorized repo."""
    from agent_guardian.utils.tool_guards import block_github_wrong_repo

    result = block_github_wrong_repo(
        _guard_tool("search_code"),
        {"q": "def main"},
        _guard_ctx({"authorized_github_owner": "", "authorized_github_repo": ""}),
    )

    assert result is not None
    assert result["error"] == "NO_AUTHORIZED_REPO"


def test_guard_allows_non_repo_tool_when_unauthorized():
    """A tool with no owner/repo args (e.g. static analysis) is allowed when unauthorized."""
    from agent_guardian.utils.tool_guards import block_github_wrong_repo

    result = block_github_wrong_repo(
        _guard_tool("run_static_analysis"),
        {},
        _guard_ctx({"authorized_github_owner": "", "authorized_github_repo": ""}),
    )

    assert result is None


def test_guard_allows_matching_repo():
    """A repo-scoped call matching the authorized repo is allowed (ingestion regression)."""
    from agent_guardian.utils.tool_guards import block_github_wrong_repo

    result = block_github_wrong_repo(
        _guard_tool("github_ingest_repository"),
        {"owner": "acme", "repo": "toolkit"},
        _guard_ctx({"authorized_github_owner": "acme", "authorized_github_repo": "toolkit"}),
    )

    assert result is None


def test_guard_blocks_wrong_repo_when_authorized():
    """A call to a different repo than the authorized one is still blocked (existing behavior)."""
    from agent_guardian.utils.tool_guards import block_github_wrong_repo

    result = block_github_wrong_repo(
        _guard_tool("github_get_file_contents"),
        {"owner": "google", "repo": "adk-python", "path": "x.py"},
        _guard_ctx({"authorized_github_owner": "acme", "authorized_github_repo": "toolkit"}),
    )

    assert result is not None
    assert result["error"] == "UNAUTHORIZED_REPO"


@pytest.mark.parametrize("approve_word", ["approve", "approved", "yes", "proceed", "apply fixes", "__AG_APPROVE_REMEDIATION__"])
def test_apply_hitl_remediation_commands_approve(mock_callback_context, approve_word):
    from agent_guardian.utils.callbacks import _apply_hitl_remediation_commands

    mock_callback_context.state["user_request"] = approve_word
    mock_callback_context.state["remediation_plan"] = '{"pr_title": "Fix"}'
    _apply_hitl_remediation_commands(mock_callback_context)

    assert mock_callback_context.state["remediation_approved"] is True
    assert mock_callback_context.state["remediation_skipped"] is False
    assert mock_callback_context.state["remediation_pending_approval"] is False


@pytest.mark.parametrize("skip_word", ["skip", "cancel", "no", "reject", "__AG_SKIP_REMEDIATION__"])
def test_apply_hitl_remediation_commands_skip(mock_callback_context, skip_word):
    from agent_guardian.utils.callbacks import _apply_hitl_remediation_commands

    mock_callback_context.state["user_request"] = skip_word
    mock_callback_context.state["remediation_plan"] = '{"pr_title": "Fix"}'
    _apply_hitl_remediation_commands(mock_callback_context)

    assert mock_callback_context.state["remediation_skipped"] is True
    assert mock_callback_context.state["remediation_approved"] is False


def test_apply_hitl_remediation_commands_commit_id(mock_callback_context):
    from agent_guardian.utils.callbacks import _apply_hitl_remediation_commands

    mock_callback_context.state["user_request"] = "EA-1234"
    mock_callback_context.state["remediation_plan"] = '{"pr_title": "Fix"}'
    mock_callback_context.state["remediation_status"] = "pending_commit_id"
    _apply_hitl_remediation_commands(mock_callback_context)

    assert mock_callback_context.state["remediation_commit_id"] == "EA-1234"
    assert mock_callback_context.state["remediation_status"] == "commit_id_provided"

