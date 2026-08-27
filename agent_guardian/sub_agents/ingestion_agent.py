from __future__ import annotations

"""
Ingestion Agent — uses fast model for quick routing/extraction.

Role in Pipeline:
This agent runs at the beginning of the `review_pipeline` (in parallel with `confluence_rules_agent`).
Its purpose is to fetch the target codebase (either from an uploaded ZIP or a remote Git repository),
parse it, apply dependency-aware topological sorting, truncate if necessary to fit within token budgets,
and split the content into `code_logic`, `code_config`, and `code_docs`.

State Interactions:
- Reads: `user_request`, `uploaded_zip_path`
- Writes: `raw_codebase`, `code_logic`, `code_config`, `code_docs`, `is_large_codebase`, `module_map`, `logic_file_count`
"""

import os
import re
import logging
from collections import defaultdict
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from agent_guardian.config import Config
from agent_guardian.prompts import INGESTION_PROMPT
from agent_guardian.tools import (
    parse_uploaded_files,
    read_artifact_file,
    github_get_file_contents,
    github_list_directory_contents,
    github_get_multiple_files,
    github_list_multiple_directories,
    github_get_recursive_tree,
    github_ingest_repository,
    bitbucket_ingest_repository,
)
from agent_guardian.tools.governance_tools import scan_governance
from ..utils.compat import get_binary_path
from ..utils.mcp_factory import get_github_mcp_toolset, GITHUB_INGEST_TOOLS
from ..utils.token_utils import synthesis_budget_callback
from ..utils.tool_guards import block_github_misuse
from ..utils.resilience import safe_callback

logger = logging.getLogger(__name__)
_cfg = Config()

_tools = [
    parse_uploaded_files,
    read_artifact_file,
    github_get_file_contents,
    github_list_directory_contents,
    github_get_multiple_files,
    github_list_multiple_directories,
    github_get_recursive_tree,
    github_ingest_repository,
    bitbucket_ingest_repository,
    scan_governance,
]

_bb_user = os.environ.get("BITBUCKET_USERNAME", "")
_bb_pass = os.environ.get("BITBUCKET_APP_PASSWORD", "")

# Shared GitHub MCP toolset built once in mcp_factory (wider ingestion read filter).
# None when GITHUB_TOKEN / npx are unavailable; the REST fallback tools above still work.
_github_mcp = get_github_mcp_toolset(GITHUB_INGEST_TOOLS)
if _github_mcp is not None:
    _tools.append(_github_mcp)
    logger.info("Loaded shared GitHub MCP tools (ingestion filter + REST fallback).")


def preprocess_ipynb(content_json: str) -> str:
    """
    Extracts code and markdown cells from an .ipynb JSON string.
    Removes outputs and metadata to optimize for LLM context.
    """
    import json

    try:
        nb = json.loads(content_json)
        cells = nb.get("cells", [])
        output = []
        for cell in cells:
            ctype = cell.get("cell_type")
            source = "".join(cell.get("source", []))
            if ctype == "code":
                output.append(f"```python\n{source}\n```")
            elif ctype == "markdown":
                output.append(source)
        return "\n\n".join(output)
    except json.JSONDecodeError:
        return content_json  # Not valid JSON — return raw as fallback
    except Exception as e:
        logger.warning("preprocess_ipynb: unexpected error (%s); returning raw content.", e)
        return content_json


def is_binary_content(content: str) -> bool:
    """Heuristic to detect binary content in a string."""
    if not content:
        return False
    # Check for null bytes or high concentration of non-printable chars
    return "\x00" in content or (len([c for c in content[:512] if ord(c) > 127]) / min(len(content), 512) > 0.3)


@safe_callback
async def check_mcp_environment_callback(callback_context: CallbackContext):
    """
    Checks if the required binaries for MCP tools are present in the environment.
    If missing, it yields a warning event to the user.
    """
    uv_path = get_binary_path("uv")
    npx_path = get_binary_path("npx")

    if not uv_path and not npx_path:
        logger.warning("Ingestion: Neither 'uv' nor 'npx' found on this instance. MCP tools will be unavailable.")
        # In a real ADK app, you might yield a System event or inject state.
        # For now, we'll inject a system note into the state for the LLM to see.
        callback_context.state["mcp_environment_warning"] = (
            "[SYSTEM WARNING: Environment missing 'uv' or 'npx'. "
            "Ingestion will fallback to basic REST tools, which may be less performant.]"
        )
    else:
        logger.info(f"Ingestion: MCP environment check passed (uv={uv_path}, npx={npx_path}).")


def block_github_when_zip_uploaded_callback(tool, args, tool_context):
    """Re-export shared guard so the agent definition stays self-contained."""
    return block_github_misuse(tool, args, tool_context)


def _topological_sort_python_files(logic_files: dict[str, str]) -> list[str]:
    """
    Dependency-Aware Topological Sort (Kahn's Algorithm).
    Strategy: Parse AST of Python files to find imports. Build a directed
    graph where A -> B means "A imports B" (A depends on B). Sort so B comes
    before A in the context.
    """
    import ast
    from collections import deque

    graph = {}  # mod_p -> [dependents]
    in_degree = {}  # mod_p -> int
    py_files = {f: c for f, c in logic_files.items() if f.endswith(".py")}

    # 1. Map files to module namespaces (e.g., 'src/api.py' -> 'src.api')
    module_to_file = {}
    for fname in py_files:
        mod_name = fname.replace("\\", "/").replace(".py", "").replace("/", ".")
        module_to_file[mod_name] = fname
        if mod_name.endswith(".__init__"):
            module_to_file[mod_name[:-9]] = fname

    def _resolve_import(module: str, level: int, current_fname: str) -> str | None:
        def _prefix_match(mod_name: str) -> str | None:
            if not mod_name:
                return None
            parts = mod_name.split(".")
            while parts:
                candidate = ".".join(parts)
                if candidate in module_to_file:
                    return module_to_file[candidate]
                parts.pop()
            return None

        if level == 0:
            return _prefix_match(module)
        parts = current_fname.replace("\\", "/").split("/")
        parts.pop()  # remove file name
        for _ in range(level - 1):
            if parts:
                parts.pop()
            else:
                return None
        base_mod = ".".join(parts)
        full_mod = f"{base_mod}.{module}" if base_mod and module else base_mod or module
        return _prefix_match(full_mod)

    # 2. Extract AST imports
    for fname, block in py_files.items():
        in_degree[fname] = 0  # Ensure node exists in degree map
        source = block.split(f"--- {fname} ---")[1] if f"--- {fname} ---" in block else block

        source = source.strip()
        code_match = re.search(r"```(?:python|py)?\n(.*?)\n```", source, re.DOTALL | re.IGNORECASE)
        if code_match:
            source = code_match.group(1)
        else:
            lines = source.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            source = "\n".join(lines)

        dependencies = set()
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dep_fname = _resolve_import(alias.name, 0, fname)
                        if dep_fname and dep_fname != fname:
                            dependencies.add(dep_fname)
                elif isinstance(node, ast.ImportFrom):
                    level = node.level
                    module = node.module or ""
                    dep_fname = _resolve_import(module, level, fname)

                    if dep_fname and dep_fname != fname:
                        dependencies.add(dep_fname)
                    elif node.names:
                        for alias in node.names:
                            sub_mod = f"{module}.{alias.name}" if module else alias.name
                            dep_fname_sub = _resolve_import(sub_mod, level, fname)
                            if dep_fname_sub and dep_fname_sub != fname:
                                dependencies.add(dep_fname_sub)
        except SyntaxError:
            pass  # Legitimately unparseable source snippet — skip
        except Exception as e:
            logger.debug("AST dependency parse failed for %s (%s: %s); skipping.", fname, type(e).__name__, e)

        for dep_fname in dependencies:
            graph.setdefault(dep_fname, []).append(fname)
            in_degree[fname] = in_degree.get(fname, 0) + 1

    try:
        # 3. Kahn's Algorithm with Cycle Resolution
        sorted_py_files = []
        queue = deque([f for f in py_files if in_degree.get(f, 0) == 0])

        while queue:
            curr = queue.popleft()
            sorted_py_files.append(curr)
            for dependent in graph.get(curr, []):
                in_degree[dependent] = in_degree.get(dependent, 0) - 1
                if in_degree.get(dependent, 0) == 0:
                    queue.append(dependent)

        cyclic_files = [f for f in py_files if in_degree.get(f, 0) > 0]
        while cyclic_files:
            target = min(cyclic_files, key=lambda f: in_degree.get(f, 0))
            in_degree[target] = 0
            queue.append(target)

            while queue:
                curr = queue.popleft()
                sorted_py_files.append(curr)
                for dependent in graph.get(curr, []):
                    if in_degree.get(dependent, 0) > 0:
                        in_degree[dependent] = in_degree.get(dependent, 0) - 1
                        if in_degree.get(dependent, 0) == 0:
                            queue.append(dependent)
            cyclic_files = [f for f in py_files if in_degree.get(f, 0) > 0]

        return sorted_py_files
    except Exception as e:
        logger.warning(f"Topological sort failed: {e}")
        return list(py_files.keys())


def _truncate_logic(logic_parts: list[str], callback_context: CallbackContext) -> str:
    """
    Token-Aware Truncation.
    Precise truncation to budget, marking large codebases if needed.
    """
    from agent_guardian.utils.token_utils import expert_token_manager

    _MAX_LOGIC_TOKENS = 30_000

    logic_str = expert_token_manager.truncate_to_budget(logic_parts, _MAX_LOGIC_TOKENS)

    if len(logic_str) < sum(len(p) for p in logic_parts):
        logger.warning(f"Ingestion: code_logic truncated to {_MAX_LOGIC_TOKENS} tokens.")
        callback_context.state["is_large_codebase"] = True

    return logic_str


async def split_codebase_callback(callback_context: CallbackContext):
    """
    Performance Optimization: Splits raw_codebase into domain-specific keys
    after ingestion is complete. This implements a Divide & Conquer pattern
    to reduce context size for expert agents.
    """
    # Ensure critical context keys are ALWAYS initialized to prevent KeyErrors in experts
    from agent_guardian.state import ReviewState

    default_state = ReviewState().model_dump()
    for k, v in default_state.items():
        if k not in callback_context.state:
            callback_context.state[k] = v

    # === OPTIMIZATION: Bypassing LLM Truncation ===
    # For large codebases, the LLM will hit MAX_TOKENS and fail to echo the full string.
    # To fix this, we directly extract the parsed codebase from the ToolResponse in
    # session events / history.  We check ALL ingestion tools and accumulate results
    # from multiple batched calls (e.g. github_get_multiple_files in batches of 30).
    _INGESTION_TOOLS = {
        "parse_uploaded_files",
        "read_artifact_file",
        "github_get_multiple_files",
        "github_get_file_contents",
        "github_ingest_repository",
        "bitbucket_ingest_repository",
    }
    extracted_parts = []  # collect from potentially multiple tool calls

    def _extract_tool_content(parts):
        """Scan a list of message parts for ingestion tool responses."""
        if not parts:
            return
        for part in parts:
            fn_resp = getattr(part, "function_response", None)
            if not fn_resp:
                continue
            part_name = getattr(fn_resp, "name", "")
            if part_name not in _INGESTION_TOOLS:
                continue
            try:
                resp = fn_resp.response
                content = ""

                # Robustly normalize tool response to a dict (handles Struct/Pydantic/etc.)
                if resp is not None and not isinstance(resp, (dict, str)):
                    if hasattr(resp, "model_dump"):
                        resp = resp.model_dump()
                    elif hasattr(resp, "to_dict"):
                        resp = resp.to_dict()
                    elif hasattr(resp, "__dict__"):
                        resp = {k: v for k, v in vars(resp).items() if not k.startswith("_")}

                if isinstance(resp, dict):
                    # Skip failed attempts (e.g. a first call with a wrong path).
                    # A later retry may have succeeded; an error blob must never
                    # poison the accumulated raw_codebase.
                    # Exception: preserve [INGESTION_FAILED] sentinels from tools
                    # like bitbucket_ingest_repository so they surface a specific
                    # error instead of the generic "no files" sentinel.
                    if str(resp.get("status", "")).lower() == "error":
                        err_codebase = resp.get("codebase", "") or ""
                        if err_codebase.lstrip().startswith("[INGESTION_FAILED]"):
                            # Write specific error directly so the gate router surfaces it.
                            callback_context.state["code_logic"] = err_codebase
                            callback_context.state["code_config"] = err_codebase
                            callback_context.state["code_docs"] = err_codebase
                            return
                        continue
                    # github_ingest_repository surfaces a coverage manifest so the
                    # report can be honest about what was excluded / truncated.
                    if part_name == "github_ingest_repository":
                        if resp.get("skipped"):
                            callback_context.state["ingest_skipped"] = resp.get("skipped")
                        if resp.get("truncated_tree"):
                            callback_context.state["ingest_truncated"] = True
                    # parse_uploaded_files returns {"codebase": "..."}
                    content = resp.get("codebase", "")
                    if content.lstrip().startswith("[SYSTEM ERROR"):
                        continue
                    if not content:
                        # github_get_file_contents returns {"content": "...", "path": "..."}
                        # Wrap as --- path --- block so the downstream parser recognises it
                        file_content = resp.get("content", "") or resp.get("result", "")
                        file_path = resp.get("path", "unknown")
                        if file_content:
                            content = f"--- {file_path} ---\n{file_content}"
                elif isinstance(resp, str):
                    # github_get_multiple_files returns a plain string
                    # already formatted as "--- path ---\ncontent"
                    # Skip pruning sentinels left by deferred history pruning.
                    if resp.startswith("[PRUNED:"):
                        continue
                    content = resp

                if content and len(content) > 20:
                    extracted_parts.append(content)
            except Exception:
                pass

    # PRIMARY: Check session.events — includes the CURRENT agent's tool responses
    # which may not yet appear in .history when after_agent_callback fires.
    # _review_event_horizon (set by constitution_callback) marks the event index
    # at which THIS review started; events before it belong to prior reviews and
    # must be skipped to prevent their ZIP content from contaminating this run.
    event_horizon = callback_context.state.get("_review_event_horizon", 0)
    if hasattr(callback_context, "session") and getattr(callback_context.session, "events", None):
        for idx, event in enumerate(callback_context.session.events):
            if idx < event_horizon:
                continue
            event_content = getattr(event, "content", None)
            if event_content and getattr(event_content, "parts", None):
                _extract_tool_content(event_content.parts)

    # FALLBACK: Also check .history (some ADK versions store events differently)
    if not extracted_parts:
        if hasattr(callback_context, "history") and callback_context.history:
            for msg in callback_context.history:
                if getattr(msg, "parts", None):
                    _extract_tool_content(msg.parts)

    extracted_raw = "\n\n".join(extracted_parts) if extracted_parts else None

    # If we extracted the full text directly from the tool, it overrides the LLM's
    # (potentially truncated/empty) output.  Also write it back to state so the
    # snapshot artifact and any downstream reader of raw_codebase gets full content.
    pruning_pending = False
    if extracted_raw:
        logger.info(
            f"Successfully bypassed LLM output: extracted {len(extracted_raw)} chars "
            f"from {len(extracted_parts)} tool response(s)!"
        )
        raw = extracted_raw
        callback_context.state["raw_codebase"] = raw
        # Defer history pruning until we have confirmed code_logic is populated.
        # Pruning before parsing risks losing the raw response on a partial failure.
        pruning_pending = True
    else:
        raw = callback_context.state.get("raw_codebase", "")

    # =========================================================================
    # FAIL-LOUD SENTINEL: If no codebase was fetched (no tool calls, empty
    # response, or LLM hallucinated a wrap-up without invoking any ingestion
    # tool), surface the failure into every downstream key. Experts are
    # instructed to detect [INGESTION_FAILED] and refuse to invent findings.
    # =========================================================================
    if not isinstance(raw, str) or not raw:
        logger.error(
            "split_codebase_callback: raw_codebase is EMPTY. "
            "No ingestion tool was called or all responses were empty. "
            "Writing [INGESTION_FAILED] sentinel to downstream state keys."
        )
        sentinel = (
            "[INGESTION_FAILED] No codebase was fetched. The ingestion agent "
            "did not call any tool, or all tool responses were empty. "
            "Experts: STOP — do NOT invent file paths, code, or findings. "
            "Output a single finding describing the ingestion failure."
        )
        callback_context.state["code_logic"] = sentinel
        callback_context.state["code_config"] = sentinel
        callback_context.state["code_docs"] = sentinel
        callback_context.state["is_large_codebase"] = False
        if "confluence_rules" not in callback_context.state:
            callback_context.state["confluence_rules"] = (
                "[CONFLUENCE_UNAVAILABLE] No Confluence rules fetched. "
                "Use built-in baselines and DO NOT claim Confluence validation."
            )
        return

    # Parse collected files into logic, config, docs
    logic_files = {}  # fname -> content_block
    config_parts = []
    docs_parts = []

    # Buckets are intentionally broad so that the denylist-based deterministic
    # ingestion (github_ingest_repository / parse_uploaded_files) never silently
    # drops a captured file. Anything textual that isn't clearly logic or docs is
    # preserved under config rather than discarded.
    _LOGIC_EXTS = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".java",
        ".ipynb",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".kts",
        ".scala",
        ".m",
        ".sh",
        ".bash",
        ".zsh",
        ".tf",
        ".proto",
        ".graphql",
        ".sql",
    }
    _DOCS_EXTS = {".md", ".txt", ".rst", ".adoc"}

    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and line.endswith(" ---"):
            fname = line[4:-4].strip()
            # Exclude GitNexus directory as per user request
            if "GitNexus/" in fname.replace("\\", "/") or fname.startswith("GitNexus"):
                i += 1
                while i < len(lines) and not (lines[i].startswith("--- ") and lines[i].endswith(" ---")):
                    i += 1
                continue

            ext = os.path.splitext(fname)[1].lower()
            content_buf = []
            i += 1
            while i < len(lines) and not (lines[i].startswith("--- ") and lines[i].endswith(" ---")):
                content_buf.append(lines[i])
                i += 1

            content_str = "\n".join(content_buf)

            # Skip binary files that might have been accidentally ingested
            if is_binary_content(content_str):
                logger.warning(f"Ingestion: Skipping binary file {fname}")
                continue

            # Pre-process IPYNB files for better LLM context
            if ext == ".ipynb":
                content_str = preprocess_ipynb(content_str)

            file_block = f"\n--- {fname} ---\n" + content_str

            if ext in _LOGIC_EXTS:
                logic_files[fname] = file_block
            elif ext in _DOCS_EXTS:
                docs_parts.append(file_block)
            else:
                # config (.yaml/.json/.toml/...) AND any other ingestible text
                # (go.mod, Dockerfile, .lock, unknown extensions) — preserved so
                # the deterministic ingest never silently discards a file.
                config_parts.append(file_block)
            continue
        i += 1

    # Detection of explicit system errors — only fatal when NOTHING was parsed.
    # A failed first tool attempt followed by a successful retry leaves both an
    # error blob and real file blocks in raw; the real files win.
    if not logic_files and not config_parts and not docs_parts:
        logger.error(f"Ingestion produced no parseable file blocks. raw head: {raw[:200]!r}")
        raw_head = raw[:2000]
        if is_binary_content(raw_head):
            # Never embed binary bytes into LLM-facing state.
            raw_head = "[binary content omitted]"
        sentinel = (
            f"[INGESTION_FAILED] No parseable source files were ingested. Raw ingestion output (truncated): {raw_head}"
        )
        callback_context.state["code_logic"] = sentinel
        callback_context.state["code_config"] = sentinel
        callback_context.state["code_docs"] = sentinel
        return

    # Apply Topological Sort (Dependency-Aware)
    sorted_py_files = _topological_sort_python_files(logic_files)

    # Combine sorted Python files with other logic files (TS, JS, etc.)
    final_logic_parts = [logic_files[f] for f in sorted_py_files]
    final_logic_parts.extend([block for f, block in logic_files.items() if not f.endswith(".py")])

    # Apply Token-Aware Truncation
    callback_context.state["code_logic"] = _truncate_logic(final_logic_parts, callback_context)
    callback_context.state["code_config"] = "\n".join(config_parts) if config_parts else ""
    callback_context.state["code_docs"] = "\n".join(docs_parts) if docs_parts else ""

    # Ensure aggregate state doesn't blow the context window for the next agent (planning_agent)
    await synthesis_budget_callback(callback_context)

    # === NEW: Capture Pre-Flight Scan Results ===
    # The ingestion agent performs a pre-flight scan and summarizes it in text.
    # We extract this summary if present.

    # Safely get last message from history or events
    last_msg = None
    if hasattr(callback_context, "history") and callback_context.history:
        last_msg = callback_context.history[-1]
    elif hasattr(callback_context, "session") and getattr(callback_context.session, "events", None):
        for event in reversed(callback_context.session.events):
            if event.author == callback_context.agent_name and event.content:
                last_msg = event.content
                break

    if last_msg and getattr(last_msg, "parts", None):
        for part in last_msg.parts:
            if getattr(part, "text", None) and "=== PRE-FLIGHT GOVERNANCE SCAN ===" in part.text:
                scan_summary = part.text.split("=== PRE-FLIGHT GOVERNANCE SCAN ===")[1].strip()
                callback_context.state["pre_flight_governance_scan"] = scan_summary
                logger.info("Ingestion: Extracted pre-flight governance scan summary.")

    # === DEFERRED HISTORY PRUNING ===
    # We deferred pruning the massive ingestion tool responses from session.events
    # until we confirmed code_logic is populated. Doing it earlier risks losing the
    # raw response on a partial parse failure (binary file, encoding issue, etc.).
    if pruning_pending and len(callback_context.state.get("code_logic", "")) > 200:
        if hasattr(callback_context, "session") and getattr(callback_context.session, "events", None):
            pruned_count = 0
            for event in callback_context.session.events:
                event_content = getattr(event, "content", None)
                if event_content and getattr(event_content, "parts", None):
                    for part in event_content.parts:
                        fn_resp = getattr(part, "function_response", None)
                        if fn_resp and getattr(fn_resp, "name", "") in _INGESTION_TOOLS:
                            if isinstance(fn_resp.response, (dict, str)):
                                # Use dict so _extract_tool_content's codebase=="" path skips it,
                                # not the isinstance(str) path that only checks for "[PRUNED:" prefix.
                                fn_resp.response = {"status": "pruned", "codebase": ""}
                                pruned_count += 1
            if pruned_count:
                logger.info(f"Pruned {pruned_count} massive ingestion events from history (post-parse).")

    # === NEW: Comprehensive Module Mapping ===
    # This helps experts navigate large codebases and supports "Parallel Module Analysis" intent.
    # We now include ALL files (logic, config, docs) for a complete inventory.
    all_files = list(logic_files.keys()) + [
        re.search(r"--- (.*?) ---", p).group(1) for p in config_parts + docs_parts if re.search(r"--- (.*?) ---", p)
    ]

    module_map = defaultdict(list)
    for fname in all_files:
        path_parts = fname.replace("\\", "/").split("/")
        if len(path_parts) > 1:
            module_name = "/".join(path_parts[: min(len(path_parts) - 1, 2)])
        else:
            module_name = "root"
        module_map[module_name].append(fname)

    callback_context.state["module_map"] = dict(module_map)
    callback_context.state["logic_file_count"] = len(logic_files)
    callback_context.state["total_file_count"] = len(all_files)

    if len(callback_context.state["code_logic"]) > 150000:
        logger.info(
            f"Logic is large ({len(callback_context.state['code_logic'])} chars); marking IS_LARGE_CODEBASE=true."
        )
        callback_context.state["is_large_codebase"] = True
    else:
        callback_context.state["is_large_codebase"] = False

    # === ARTIFACT STORAGE: Source Snapshot ===
    # Use a short, stable filename ("src.md") to avoid overflowing Windows' 260-char MAX_PATH
    # when combined with deep nested ADK artifact paths on OneDrive-synced directories
    # (`<root>/.../artifacts/<name>/versions/0/<name>`).
    snapshot_filename = "src.md"
    try:
        snapshot_content = f"# Source Snapshot\n\nGenerated during ingestion phase.\n\n{raw}"
        artifact = types.Part(inline_data=types.Blob(data=snapshot_content.encode("utf-8"), mime_type="text/markdown"))
        await callback_context.save_artifact(filename=snapshot_filename, artifact=artifact)
        callback_context.state["source_artifact_name"] = snapshot_filename
        logger.info(f"Ingestion: Source snapshot artifact saved to {snapshot_filename}.")
    except Exception as e:
        logger.warning(f"Ingestion: Failed to save snapshot artifact: {e}")

    logger.info(
        f"Optimization: Split codebase into logic ({len(final_logic_parts)} sorted), config ({len(config_parts)}), docs ({len(docs_parts)})"
    )


ingestion_agent = LlmAgent(
    name="ingestion_agent",
    model=_cfg.agent_settings.ingestion_model,
    description="Fetches code from GitHub, Bitbucket, or local sources.",
    instruction=(
        INGESTION_PROMPT
        + "\n\n### UPLOADED ZIP PATH (if present, this OVERRIDES any URL):\n{uploaded_zip_path?}"
        + "\n\n### AUTHORIZED BRANCH/REF:\n{authorized_github_ref?}"
        + "\n\n### USER REQUEST:\n{user_request}"
    ),
    tools=_tools,
    output_key="raw_codebase",
    # State-only, like the experts: the codebase source (URL / pasted code) is in
    # {user_request} and the upload path in {uploaded_zip_path}, both refreshed
    # every run. Reading conversation history would let a NEW upload re-ground on a
    # PREVIOUS turn's "[System Note: ZIP at <old-path>]" / fetched files when the
    # session is reused — i.e. "relies on previously uploaded files". 'none' makes
    # state the single source of truth, so pre_review_reset_node fully controls it.
    include_contents="none",
    before_agent_callback=check_mcp_environment_callback,
    before_tool_callback=block_github_when_zip_uploaded_callback,
    after_agent_callback=split_codebase_callback,
    generate_content_config=_cfg.safety_config,
)
