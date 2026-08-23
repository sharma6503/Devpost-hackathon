from __future__ import annotations
import asyncio
import inspect
import pytest
from agent_guardian.agent import constitution_callback
from agent_guardian.sub_agents.ingestion_agent import split_codebase_callback


def _run_callback(cb, ctx):
    """Invoke a callback that may be sync or async."""
    result = cb(ctx)
    if inspect.iscoroutine(result):
        asyncio.run(result)


def test_instruction_injection_robustness(mock_tool_context):
    """Verifies that constitution_callback injects required metadata to prevent KeyErrors."""
    _run_callback(constitution_callback, mock_tool_context)

    # Check for critical metadata keys used in prompt templates
    assert "today" in mock_tool_context.state
    assert "eval_pass_threshold" in mock_tool_context.state
    assert "default_repo" in mock_tool_context.state
    assert "base_branch" in mock_tool_context.state

    # New invariant: confluence_rules must be initialized to a sentinel so
    # experts never see an empty placeholder.
    assert mock_tool_context.state["confluence_rules"].startswith("[CONFLUENCE_UNAVAILABLE]")


@pytest.mark.asyncio
async def test_ingestion_markdown_hardening(mock_tool_context):
    """Verifies that ingestion callback can handle messy markdown fences in source code."""
    # Simulate tool returning code wrapped in markdown fences
    mock_tool_context.state["raw_codebase"] = """--- main.py ---
```python
def run():
    print("hardened")
```
"""
    # This should NOT fail with SyntaxError during topological sort
    await split_codebase_callback(mock_tool_context)

    # Verify content was extracted (topological sort logic should have succeeded or fallen back safely)
    assert "main.py" in mock_tool_context.state["code_logic"]


@pytest.mark.asyncio
async def test_ingestion_binary_skipping(mock_tool_context):
    """Verifies that the ingestion agent skips binary content to avoid context bloat."""
    binary_data = "--- binary.bin ---\n" + "\x00\x01\x02\x03" * 100
    mock_tool_context.state["raw_codebase"] = binary_data

    await split_codebase_callback(mock_tool_context)

    assert "binary.bin" not in mock_tool_context.state["code_logic"]
    assert "binary.bin" not in mock_tool_context.state["code_config"]
