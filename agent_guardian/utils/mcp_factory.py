from __future__ import annotations

"""
mcp_factory.py — Shared MCP toolset construction.

Every review expert used to build its own GitHub MCP toolset with ~25 lines of
identical boilerplate that drifted independently (different timeouts, missing
binary-path guards). This module is the single construction site.

The returned toolsets are module-level singletons: SafeMcpToolset was designed
for sharing across parallel agents (its ``close()`` is a deliberate no-op and
tool discovery is guarded by an asyncio.Lock), so one stdio server process
serves the whole expert fleet instead of four.
"""

import functools
import logging
import os
from typing import Optional

from .compat import SafeMcpToolset, get_binary_path, invalidate_all_safe_toolsets

logger = logging.getLogger(__name__)


def invalidate_mcp_toolsets() -> None:
    """Force every shared MCP toolset to re-discover tools on its next use.

    Called once at the start of each review so a stdio session that died between
    runs is re-established instead of serving stale tool proxies. Never raises.
    """
    invalidate_all_safe_toolsets()


# Default read tool filter shared by all review experts.
GITHUB_READ_TOOLS = ("get_file_contents", "list_directory_contents", "get_tree")

# Wider read filter for ingestion (needs repo/commit/branch metadata too).
GITHUB_INGEST_TOOLS = (
    "get_file_contents",
    "list_directory_contents",
    "get_tree",
    "get_repository",
    "list_commits",
    "list_branches",
)


def _build_github_toolset(
    tool_filter: Optional[tuple[str, ...]],
    github_toolsets: str,
    timeout: int,
) -> Optional[SafeMcpToolset]:
    """Construct a SafeMcpToolset around the GitHub MCP stdio server.

    Returns None (never raises) when GITHUB_TOKEN or an npx/uv binary is missing,
    or if the server fails to start. Shared by the read/write builders below.
    """
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        logger.info("mcp_factory: GITHUB_TOKEN not set — GitHub MCP disabled.")
        return None
    if not (get_binary_path("npx") or get_binary_path("uv")):
        logger.info("mcp_factory: npx/uv not found — GitHub MCP disabled.")
        return None

    try:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
        from mcp import StdioServerParameters

        toolset = SafeMcpToolset(
            McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command="npx",
                        args=["-y", "@modelcontextprotocol/server-github"],
                        env={
                            "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
                            "GITHUB_TOOLSETS": github_toolsets,
                        },
                    ),
                    timeout=timeout,
                ),
                tool_filter=list(tool_filter) if tool_filter else None,
            )
        )
        logger.info(
            "mcp_factory: shared GitHub MCP toolset created "
            f"(toolsets={github_toolsets}, filter={'all' if not tool_filter else len(tool_filter)})."
        )
        return toolset
    except Exception as e:
        logger.warning(f"mcp_factory: GitHub MCP toolset failed to load: {e}")
        return None


@functools.lru_cache(maxsize=None)
def get_github_mcp_toolset(
    tool_filter: tuple[str, ...] = GITHUB_READ_TOOLS,
) -> Optional[SafeMcpToolset]:
    """Return a shared read-only GitHub MCP toolset, or None if unavailable.

    Requires GITHUB_TOKEN and a working npx. Memoized per ``tool_filter`` so the
    default review-expert filter and the wider ingestion filter each get one
    shared instance that parallel agents reuse.
    """
    return _build_github_toolset(tool_filter, github_toolsets="repos,contents,search", timeout=15)


@functools.lru_cache(maxsize=None)
def get_github_write_mcp_toolset() -> Optional[SafeMcpToolset]:
    """Return the shared read/write GitHub MCP toolset used by remediation.

    Unlike the read builder this exposes write toolsets (repo/files/pull_requests/
    git) and applies no tool filter, so branch/commit/PR tools are available.
    """
    return _build_github_toolset(tool_filter=None, github_toolsets="repo,files,pull_requests,git", timeout=10)


@functools.lru_cache(maxsize=None)
def get_adk_docs_toolset() -> Optional[SafeMcpToolset]:
    """Return the shared ADK-docs (mcpdoc) toolset, or None if unavailable."""
    try:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
        from mcp import StdioServerParameters

        import sys

        toolset = SafeMcpToolset(
            McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command=sys.executable,
                        args=[
                            "-m",
                            "mcpdoc.cli",
                            "--follow-redirects",
                            "--urls",
                            "AgentDevelopmentKit:https://adk.dev/llms.txt",
                        ],
                    ),
                    timeout=15,
                ),
                tool_filter=["fetch_docs", "list_doc_sources"],
            )
        )
        logger.info("mcp_factory: shared ADK-docs MCP toolset created.")
        return toolset
    except Exception as e:
        logger.warning(f"mcp_factory: ADK-docs MCP toolset failed to load: {e}")
        return None
