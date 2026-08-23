from agent_guardian.utils.mcp_factory import get_adk_docs_toolset
from agent_guardian.agent import root_agent


def test_adk_docs_mcp_factory():
    """Verify ADK Docs MCP toolset is instantiated correctly."""
    toolset = get_adk_docs_toolset()
    if toolset is not None:
        assert hasattr(toolset, "tool_filter") or hasattr(toolset, "get_tools")


def test_root_agent_has_adk_docs_mcp():
    """Verify root_agent has tools configured."""
    assert hasattr(root_agent, "tools")
    toolset = get_adk_docs_toolset()
    if toolset is not None:
        assert toolset in root_agent.tools
