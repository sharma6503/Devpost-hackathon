from __future__ import annotations

"""
Compatibility and Platform Utilities

Centralises platform-specific setup and provides a SafeMcpToolset wrapper
to prevent adk web startup crashes on Windows due to event loop conflicts.
"""

import asyncio
import base64
import glob
import json
import os
import re
import sys
import shutil
import logging
import traceback
import weakref
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Live registry of every SafeMcpToolset instance (factory singletons AND the
# standalone toolsets built in ingestion_agent / remediation_agent). A WeakSet
# so it never keeps a toolset alive on its own. invalidate_all_safe_toolsets()
# sweeps it once per review so each run re-discovers tools against a fresh
# session instead of reusing proxies bound to a previous (possibly dead) one.
_ALL_TOOLSETS: "weakref.WeakSet" = weakref.WeakSet()


def invalidate_all_safe_toolsets() -> None:
    """Drop cached tool discovery on every live SafeMcpToolset (never raises)."""
    for ts in list(_ALL_TOOLSETS):
        try:
            ts.invalidate()
        except Exception as e:  # pragma: no cover - purely defensive
            logger.debug("invalidate_all_safe_toolsets: skipped one instance: %s", e)


def get_atlassian_basic_auth() -> Optional[str]:
    """
    Constructs a Base64-encoded Basic Auth string from environment variables:
    - ATLASSIAN_EMAIL (or ATLASSIAN_USERNAME)
    - ATLASSIAN_API_TOKEN

    Returns the encoded string (e.g. 'ZW1haWw6dG9rZW4=') or None if missing.
    """
    email = os.environ.get("ATLASSIAN_EMAIL") or os.environ.get("ATLASSIAN_USERNAME")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not token:
        return None

    auth_str = f"{email}:{token}"
    return base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")


def get_atlassian_cloud_id() -> Optional[str]:
    """
    Returns a pre-configured Atlassian Cloud ID (UUID) from environment variables.
    Look for ATLASSIAN_CLOUD_ID or CONFLUENCE_CLOUD_ID.
    """
    return os.environ.get("ATLASSIAN_CLOUD_ID") or os.environ.get("CONFLUENCE_CLOUD_ID")


def load_atlassian_oauth_token() -> Optional[str]:
    """
    Load the OAuth bearer token persisted by ``mcp-remote`` for the Atlassian
    Remote MCP server (https://mcp.atlassian.com/v1/sse).

    The mcp-remote CLI stores tokens at:
        ~/.mcp-auth/mcp-remote-<version>/<server_id>_tokens.json

    Returns the most-recently-modified ``access_token`` if found, else None.
    """
    try:
        base = Path.home() / ".mcp-auth"
        if not base.exists():
            return None
        candidates = sorted(
            glob.glob(str(base / "mcp-remote-*" / "*_tokens.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        for path in candidates:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                token = data.get("access_token")
                if token:
                    return token
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"load_atlassian_oauth_token failed: {e}")
    return None


# Try to import ADK types for the wrapper, but keep it optional for pure-compat use
try:
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.base_toolset import BaseToolset
    from google.adk.tools.base_tool import BaseTool

    _ADK_AVAILABLE = True
except ImportError:
    McpToolset = object
    BaseToolset = object
    BaseTool = object
    _ADK_AVAILABLE = False

_platform_compat_done = False


def setup_platform_compat():
    """Perform any required platform-specific setup for asyncio/subprocesses.

    Idempotent — repeated calls (tests, multiple entrypoints) are no-ops.
    """
    global _platform_compat_done
    if _platform_compat_done:
        return
    _platform_compat_done = True
    if sys.platform == "win32":
        try:
            # Uvicorn/ADK Web often use SelectorEventLoop which doesn't support
            # subprocesses on Windows. ProactorEventLoop is required for MCP.
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                policy = asyncio.get_event_loop_policy()
                if hasattr(asyncio, "WindowsProactorEventLoopPolicy") and not isinstance(
                    policy, asyncio.WindowsProactorEventLoopPolicy
                ):
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                    logger.info("Windows detected: Set ProactorEventLoopPolicy for MCP/subprocess support.")
        except Exception as e:
            logger.warning(f"Could not set Windows ProactorEventLoopPolicy: {e}")

        # ADK's LoggingPlugin uses print() which defaults to the Windows system
        # codepage (CP1252/charmap). Its callbacks contain emoji characters
        # (e.g. 🚀) that CP1252 cannot encode, causing a UnicodeEncodeError
        # that surfaces as a run_sse error and aborts every audit run.
        # Reconfigure stdout/stderr to UTF-8 so all print() output is safe.
        for _stream_name in ("stdout", "stderr"):
            _stream = getattr(sys, _stream_name, None)
            if _stream and hasattr(_stream, "reconfigure"):
                try:
                    _stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception as _e:
                    logger.warning("Could not reconfigure %s to UTF-8: %s", _stream_name, _e)


def get_binary_path(name: str) -> str | None:
    """Check for existence of a binary (uvx, npx, node) in the system path."""
    return shutil.which(name)


def _sanitize_mcp_schema(schema: Any) -> Any:
    """
    Recursively sanitizes a JSON schema to comply with Gemini's strict Tool requirements:
    - Coerces list types (e.g. ["string", "null"]) to a single string (the first non-null).
    - Merges properties from anyOf, oneOf, allOf into the main properties block.
    - Removes unsupported keys: anyOf, oneOf, allOf, $defs, $id, $schema.
    - Ensures all 'properties' values are valid objects.
    """
    if not isinstance(schema, dict):
        return schema

    new_schema = {}

    # 0. Pre-process composite keywords to avoid losing properties
    # MCP tools often use anyOf/oneOf for optional/alternative parameters
    for composite in ("anyOf", "oneOf", "allOf"):
        if composite in schema and isinstance(schema[composite], list):
            for sub in schema[composite]:
                if isinstance(sub, dict):
                    # Recursively sanitize sub-schema properties
                    sub_sanitized = _sanitize_mcp_schema(sub)
                    if "properties" in sub_sanitized:
                        existing_props = new_schema.get("properties", {})
                        if not isinstance(existing_props, dict):
                            existing_props = {}
                        existing_props.update(sub_sanitized["properties"])
                        new_schema["properties"] = existing_props
                    if "required" in sub_sanitized:
                        existing_req = new_schema.get("required", [])
                        if not isinstance(existing_req, list):
                            existing_req = []
                        new_schema["required"] = list(set(existing_req + sub_sanitized["required"]))

    for k, v in schema.items():
        # 1. Skip unsupported keywords that Gemini rejects
        if k in (
            "anyOf",
            "oneOf",
            "allOf",
            "$defs",
            "$id",
            "$schema",
            "additionalProperties",
        ):
            continue

        # 2. Coerce list-based types to single strings (Gemini doesn't support type arrays)
        if k == "type" and isinstance(v, list):
            types = [t for t in v if t != "null"]
            new_schema[k] = types[0] if types else "string"
            continue

        # 3. Handle properties specifically to merge with what we found in composite blocks
        if k == "properties" and isinstance(v, dict):
            existing_props = new_schema.get("properties", {})
            if not isinstance(existing_props, dict):
                existing_props = {}
            # Deep merge/sanitize properties
            for prop_name, prop_val in v.items():
                existing_props[prop_name] = _sanitize_mcp_schema(prop_val)
            new_schema[k] = existing_props
            continue

        # 4. Recursive sanitization for other dicts (like items, etc.)
        if isinstance(v, dict):
            new_schema[k] = _sanitize_mcp_schema(v)
        elif isinstance(v, list):
            new_schema[k] = [_sanitize_mcp_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            new_schema[k] = v

    return new_schema


def _sanitize_tool_name(name: str) -> str:
    """Ensure tool name matches Gemini's regex ^[a-zA-Z_][a-zA-Z0-9_-]*$."""
    # Replace any non-alphanumeric (excluding _ and -) with _
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    # Ensure it starts with a letter or underscore
    if not re.match(r"^[a-zA-Z_]", sanitized):
        sanitized = "_" + sanitized
    return sanitized


if _ADK_AVAILABLE:

    class SanitizedMcpTool(BaseTool):
        """
        Proxy wrapper for an ADK BaseTool (usually McpTool) that lazily
        sanitizes its name and schema for Gemini compatibility.

        Key design decisions:
        - self.name          = sanitized name sent to Gemini in FunctionDeclaration
        - self._original_name = original MCP tool name used for actual dispatch
        - _get_declaration()  builds the schema directly from the sanitized dict;
          it does NOT call _to_gemini_schema() because that util expects an
          mcp.types.Tool object, not a plain dict, and returns None on dicts.
        - run_async() remaps the sanitized name back before delegating so the
          inner McpTool can find its server-side function.
        """

        def __init__(self, tool: Any):
            self._tool = tool
            self._original_name = tool.name  # preserve for dispatch
            self.name = _sanitize_tool_name(tool.name)  # Gemini-safe name
            self.description = getattr(tool, "description", "")

            for attr in (
                "require_confirmation",
                "response_modalities",
                "read_only_hint",
            ):
                if hasattr(tool, attr):
                    setattr(self, attr, getattr(tool, attr))

        @property
        def raw_mcp_tool(self):
            """Return a copy of the raw MCP tool with its inputSchema sanitized."""
            raw = getattr(self._tool, "raw_mcp_tool", None)
            if raw and hasattr(raw, "inputSchema"):
                import copy

                cloned = copy.copy(raw)
                cloned.inputSchema = _sanitize_mcp_schema(raw.inputSchema)
                return cloned
            return raw

        def _get_declaration(self):
            """Build a FunctionDeclaration directly from the sanitized schema dict.

            Intentionally avoids _to_gemini_schema() because that utility
            expects an mcp.types.Tool object; passing a plain dict causes it to
            return None which results in MALFORMED_FUNCTION_CALL.
            """
            raw = self.raw_mcp_tool
            if not raw:
                return None
            try:
                schema: dict = raw.inputSchema or {}
                from google.genai.types import FunctionDeclaration, Schema, Type

                # Build a google.genai Schema from the sanitized dict
                def _dict_to_schema(d: dict) -> "Schema":
                    """Recursively convert a sanitized JSON-schema dict to google.genai.Schema."""
                    type_map = {
                        "string": Type.STRING,
                        "integer": Type.INTEGER,
                        "number": Type.NUMBER,
                        "boolean": Type.BOOLEAN,
                        "array": Type.ARRAY,
                        "object": Type.OBJECT,
                    }
                    t = type_map.get(d.get("type", "string"), Type.STRING)
                    props = None
                    if "properties" in d and isinstance(d["properties"], dict):
                        props = {k: _dict_to_schema(v) for k, v in d["properties"].items()}
                    items = None
                    if "items" in d and isinstance(d["items"], dict):
                        items = _dict_to_schema(d["items"])
                    return Schema(
                        type=t,
                        description=d.get("description", ""),
                        properties=props,
                        required=d.get("required"),
                        items=items,
                        enum=d.get("enum"),
                        nullable=True if d.get("nullable") else None,
                    )

                parameters = _dict_to_schema(schema)
                decl = FunctionDeclaration(
                    name=self.name,
                    description=self.description,
                    parameters=parameters,
                )
                logger.debug(f"SanitizedMcpTool: built declaration for '{self.name}' (orig='{self._original_name}')")
                return decl
            except Exception as e:
                logger.error(
                    f"SanitizedMcpTool: failed to build declaration for '{self.name}': {e}",
                    exc_info=True,
                )
                return None

        def to_function_declaration(self):
            return self._get_declaration()

        async def run_async(self, args: dict, tool_context: Any) -> Any:
            """
            ADK calls run_async(args, tool_context) for tool execution.
            The inner McpTool dispatches by its ORIGINAL name on the MCP server,
            so we must temporarily restore it before delegating.
            """
            # Restore original name so the inner tool's dispatch logic matches
            original_tool_name = self._tool.name
            self._tool.name = self._original_name
            try:
                return await self._tool.run_async(args, tool_context)
            finally:
                self._tool.name = original_tool_name  # always restore

        async def __call__(self, *args, **kwargs):
            return await self._tool(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._tool, name)

    class SafeMcpToolset(BaseToolset):
        """
        A wrapper for McpToolset that catches ConnectionErrors and anyio.BrokenResourceErrors
        during discovery (canonical_tools) and execution.

        Includes an asyncio.Lock to prevent TaskGroup/ExceptionGroup races when
        ParallelAgents try to initialize a shared MCP session concurrently.

        Now includes:
        - Deep Schema Sanitization for Gemini compatibility.
        - Cross-platform Command Auto-fix: detects if npx.cmd/uvx.exe is used on Linux.
        - Pickling Safety: Lazy lock initialization and __getstate__ support for Agent Engine.
        """

        def __init__(self, toolset: McpToolset):
            self._toolset = toolset
            self.connection_params = getattr(toolset, "connection_params", None)
            self._lock = None  # Lazy init to support pickling
            self._discovered_tools = None
            self.last_error: Optional[str] = None

            # Register for per-review invalidation (see invalidate_all_safe_toolsets).
            try:
                _ALL_TOOLSETS.add(self)
            except Exception:  # pragma: no cover - registry is best-effort
                pass

            # Auto-fix commands for cross-platform pickling
            self._fix_command_if_needed()

        def invalidate(self) -> None:
            """Drop cached discovery so the next get_tools() re-discovers tools.

            The toolset is built once at import and bound into each expert agent.
            Without this, a successful first review caches tool proxies tied to
            that run's stdio session; a later review reuses them even if the
            session has since died. Re-discovery re-establishes the session
            (ADK's McpToolset connects lazily) — cheap vs. rebuilding the process.
            """
            self._discovered_tools = None
            self.last_error = None

        def __getstate__(self):
            """Prepare state for pickling (deployment to Reasoning Engine)."""
            state = self.__dict__.copy()
            # asyncio.Lock and discovered tools (proxies) cannot be pickled reliably
            state["_lock"] = None
            state["_discovered_tools"] = None
            return state

        def __setstate__(self, state):
            """Restore state after unpickling."""
            self.__dict__.update(state)
            # Re-register on the unpickling process so invalidation reaches it.
            try:
                _ALL_TOOLSETS.add(self)
            except Exception:  # pragma: no cover - registry is best-effort
                pass

        def _get_lock(self) -> asyncio.Lock:
            """Thread-safe lazy initialization of the asyncio.Lock."""
            if self._lock is None:
                self._lock = asyncio.Lock()
            return self._lock

        def _fix_command_if_needed(self):
            """Ensures command name is valid for the current OS (e.g. npx.cmd -> npx on Linux)."""
            cp = getattr(self._toolset, "connection_params", None)
            if not cp:
                return

            server_params = getattr(cp, "server_params", None)
            if not server_params:
                return

            command = getattr(server_params, "command", "")
            if not command or not isinstance(command, str):
                return

            # If on Linux but command has Windows extension
            if os.name != "nt":
                if command.endswith(".cmd"):
                    new_cmd = command[:-4]
                    logger.info(f"SafeMcpToolset: Auto-fixing command '{command}' -> '{new_cmd}' for Linux.")
                    server_params.command = new_cmd
                elif command.endswith(".exe"):
                    new_cmd = command[:-4]
                    logger.info(f"SafeMcpToolset: Auto-fixing command '{command}' -> '{new_cmd}' for Linux.")
                    server_params.command = new_cmd
            # If on Windows but command is missing extension (less common issue with pickling, but good for symmetry)
            elif os.name == "nt":
                if command == "npx":
                    server_params.command = "npx.cmd"
                elif command == "uvx":
                    server_params.command = "uvx.exe"

        async def get_tools(self, context: Any) -> List[Any]:
            # Double-check locking to avoid discovery overhead while ensuring thread-safe startup
            if self._discovered_tools is not None:
                return self._discovered_tools

            async with self._get_lock():
                if self._discovered_tools is not None:
                    return self._discovered_tools

                try:
                    # Log the attempt
                    logger.info(f"SafeMcpToolset: Attempting tool discovery for {self._target_desc()}")

                    tools = await self._toolset.get_tools(context)
                    if not tools:
                        msg = f"No tools discovered for {self._target_desc()}. This often indicates an authorization failure or empty toolset on the server."
                        logger.warning(f"SafeMcpToolset: {msg}")
                        self.last_error = msg
                    else:
                        tool_names = [t.name for t in tools]
                        logger.info(
                            f"SafeMcpToolset: Discovered {len(tools)} tools for {self._target_desc()}: {tool_names}"
                        )
                        self.last_error = None

                    # Apply Sanitization to every discovered tool
                    sanitized_tools = [SanitizedMcpTool(t) for t in tools]
                    self._discovered_tools = sanitized_tools
                    return sanitized_tools
                except Exception as e:
                    # Capture deep traceback for Cloud Run debugging
                    tb = traceback.format_exc()

                    # Look for specific transport indicators
                    error_msg = str(e)
                    diag_hint = ""
                    if "401" in error_msg:
                        diag_hint = " [HINT: Unauthorized - Check API Token/Username]"
                    elif "403" in error_msg:
                        diag_hint = " [HINT: Forbidden - Check Atlassian Rovo Admin Settings]"
                    elif "BrokenResourceError" in error_msg or "stream disconnected" in error_msg.lower():
                        diag_hint = " [HINT: Network Disconnect - Check Cloud Run egress or SSE timeout]"

                    full_error = f"Critical failure during discovery for {self._target_desc()}{diag_hint}\nError: {e!r}"
                    logger.error(f"SafeMcpToolset: {full_error}\nTraceback: {tb}")
                    self.last_error = full_error

                    # Special handling for anyio
                    try:
                        import anyio

                        if isinstance(e, anyio.BrokenResourceError):
                            logger.warning(
                                "SafeMcpToolset: anyio.BrokenResourceError detected. The SSE stream was closed externally."
                            )
                    except ImportError:
                        pass

                    return []

        def _target_desc(self) -> str:
            """Build a description of the connection target."""
            cp = getattr(self._toolset, "connection_params", None)
            return getattr(getattr(cp, "server_params", None), "command", None) or getattr(cp, "url", None) or repr(cp)

        async def get_tools_with_prefix(self, context: Any) -> List[Any]:
            try:
                return await self._toolset.get_tools_with_prefix(context)
            except (Exception, BrokenPipeError, BaseException) as e:
                logger.debug(f"SafeMcpToolset connection skipped (prefix): {e}")
                return []

        async def close(self) -> None:
            """
            DO NOT delegate close() to the inner toolset by default.
            In parallel architectures, multiple agents share the same MCP toolset instance.
            If one agent finishes and closes the shared session, it breaks all other
            active agents using that session.
            """
            pass

else:

    class SafeMcpToolset:
        def __init__(self, toolset: Any):
            self.last_error = None

        def invalidate(self) -> None:
            pass

        async def get_tools(self, context: Any):
            return []

        async def get_tools_with_prefix(self, context: Any):
            return []

        async def close(self) -> None:
            pass
