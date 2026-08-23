from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from agent_guardian.sub_agents.ingestion_agent import split_codebase_callback


@pytest.mark.asyncio
async def test_split_codebase_callback(mock_tool_context):
    # Prepare state with raw_codebase
    mock_tool_context.state["raw_codebase"] = """--- main.py ---
import helper
def run(): helper.do()

--- helper.py ---
def do(): print('done')

--- config.yaml ---
api_version: v1
"""
    # Run callback
    await split_codebase_callback(mock_tool_context)

    # Verify logic, config, docs split
    assert "main.py" in mock_tool_context.state["code_logic"]
    assert "helper.py" in mock_tool_context.state["code_logic"]
    assert "api_version: v1" in mock_tool_context.state["code_config"]

    # Verify logic file count
    assert mock_tool_context.state["logic_file_count"] == 2

    # Verify module map
    assert "root" in mock_tool_context.state["module_map"]
    assert "main.py" in mock_tool_context.state["module_map"]["root"]


@pytest.mark.asyncio
async def test_topological_sort_in_callback(mock_tool_context):
    # helper.py should come BEFORE main.py because main imports helper
    mock_tool_context.state["raw_codebase"] = """--- main.py ---
import helper
print('main')

--- helper.py ---
print('helper')
"""
    await split_codebase_callback(mock_tool_context)

    logic = mock_tool_context.state["code_logic"]
    helper_pos = logic.find("--- helper.py ---")
    main_pos = logic.find("--- main.py ---")

    assert helper_pos < main_pos, "helper.py should appear before main.py in code_logic"


@pytest.mark.asyncio
async def test_callback_writes_ingestion_failed_sentinel_when_no_codebase(
    mock_tool_context,
):
    """When no tool was called and raw_codebase is empty, downstream state
    keys must contain the [INGESTION_FAILED] sentinel so experts refuse to
    invent findings.
    """
    # No raw_codebase, no events -> nothing was fetched.
    mock_tool_context.session = MagicMock()
    mock_tool_context.session.events = []

    await split_codebase_callback(mock_tool_context)

    for key in ("code_logic", "code_config", "code_docs"):
        assert key in mock_tool_context.state
        assert mock_tool_context.state[key].startswith("[INGESTION_FAILED]"), (
            f"{key} should carry [INGESTION_FAILED] sentinel, got: {mock_tool_context.state[key][:80]!r}"
        )

    # confluence_rules must also be set to a clear sentinel so experts can
    # detect the unavailable state.
    assert mock_tool_context.state["confluence_rules"].startswith("[CONFLUENCE_UNAVAILABLE]")

    # is_large_codebase must be reset to False on ingestion failure so the
    # large-codebase protocol does not run with empty state.
    assert mock_tool_context.state["is_large_codebase"] is False


@pytest.mark.asyncio
async def test_failed_first_tool_call_does_not_poison_successful_retry(
    mock_tool_context,
):
    """Regression: parse_uploaded_files fails on attempt 1 (e.g. wrong path) and
    succeeds on attempt 2. The error blob must be skipped during extraction so
    code_logic carries the real files — previously the '[SYSTEM ERROR:' check
    flagged the whole run as [INGESTION_FAILED] and the code validator reported
    'no code found'.
    """

    def _tool_event(response):
        fn_resp = MagicMock()
        fn_resp.name = "parse_uploaded_files"
        fn_resp.response = response
        part = MagicMock()
        part.function_response = fn_resp
        event = MagicMock()
        event.content.parts = [part]
        return event

    failed = _tool_event(
        {
            "status": "error",
            "codebase": "[SYSTEM ERROR: No readable source files found in the provided paths.]",
            "file_count": 0,
        }
    )
    succeeded = _tool_event(
        {
            "status": "success",
            "codebase": "--- app/main.py ---\nprint('hello')",
            "file_count": 1,
        }
    )

    mock_tool_context.session = MagicMock()
    mock_tool_context.session.events = [failed, succeeded]
    mock_tool_context.state["raw_codebase"] = ""

    await split_codebase_callback(mock_tool_context)

    assert "[INGESTION_FAILED]" not in mock_tool_context.state["code_logic"]
    assert "app/main.py" in mock_tool_context.state["code_logic"]
    assert "[SYSTEM ERROR" not in mock_tool_context.state["raw_codebase"]


@pytest.mark.asyncio
async def test_all_tool_calls_failed_writes_sentinel(mock_tool_context):
    """If every ingestion tool attempt failed, the fail-loud sentinel must
    still reach the downstream state keys."""
    fn_resp = MagicMock()
    fn_resp.name = "parse_uploaded_files"
    fn_resp.response = {
        "status": "error",
        "codebase": "[SYSTEM ERROR: No readable source files found in the provided paths.]",
        "file_count": 0,
    }
    part = MagicMock()
    part.function_response = fn_resp
    event = MagicMock()
    event.content.parts = [part]

    mock_tool_context.session = MagicMock()
    mock_tool_context.session.events = [event]
    mock_tool_context.state["raw_codebase"] = ""

    await split_codebase_callback(mock_tool_context)

    for key in ("code_logic", "code_config", "code_docs"):
        assert mock_tool_context.state[key].startswith("[INGESTION_FAILED]")


@pytest.mark.asyncio
async def test_callback_extracts_from_object_response(mock_tool_context):
    """Verify that the callback can extract codebase from an object (e.g. Pydantic) response."""

    class MockResponse:
        def __init__(self, codebase):
            self.codebase = codebase

        def model_dump(self):
            return {"codebase": self.codebase}

    mock_fn_resp = MagicMock()
    mock_fn_resp.name = "parse_uploaded_files"
    mock_fn_resp.response = MockResponse("--- file.py ---\nprint('hello')")

    mock_part = MagicMock()
    mock_part.function_response = mock_fn_resp

    mock_event = MagicMock()
    mock_event.content.parts = [mock_part]

    mock_tool_context.session = MagicMock()
    mock_tool_context.session.events = [mock_event]
    mock_tool_context.state["raw_codebase"] = ""  # Should be overridden by extracted content

    await split_codebase_callback(mock_tool_context)

    assert "print('hello')" in mock_tool_context.state["code_logic"]
    assert mock_tool_context.state["raw_codebase"] == "--- file.py ---\nprint('hello')"
