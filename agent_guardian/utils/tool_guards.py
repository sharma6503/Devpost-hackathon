"""Shared `before_tool_callback` guards.

These callbacks run before every tool invocation and can short-circuit a
call by returning a non-None dict. Used to enforce upload-vs-GitHub
precedence at the ADK runtime layer rather than relying on prompt discipline.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FORBIDDEN_SUBSTRINGS_WHEN_ZIP = (
    "github",
    "bitbucket",
    "get_repository",
    "search_code",
    "list_directory_contents",
    "get_recursive_tree",
    "get_file_contents",
    "list_multiple_directories",
)

# Remediation WRITE tools push the agreed fixes to a configured target repo — they
# are NOT source-ingestion fetches, so the "you uploaded a ZIP, use local source"
# guard must not block them. Without this exception, github_apply_remediation_plan
# (name contains "github") is blocked on every upload-based audit and the executor
# calls no tool at all.
_REMEDIATION_WRITE_SUBSTRINGS = (
    "apply_remediation_plan",
    "create_branch",
    "create_or_update_file",
    "create_pull_request",
    "delete_file",
)


def block_github_when_zip_uploaded(tool, args, tool_context):
    """HARD GUARD: skip any github/bitbucket tool when an upload is in scope.

    Returning a dict from a `before_tool_callback` causes ADK to use that
    dict as the tool response WITHOUT invoking the underlying tool.
    """
    try:
        state = getattr(tool_context, "state", None) or {}
        zip_path = state.get("uploaded_zip_path")
        source_artifact_path = state.get("source_artifact_path")
        # Either signal counts as "user gave us local source — don't go remote".
        if not zip_path and not source_artifact_path:
            return None

        tool_name = getattr(tool, "name", "") or getattr(tool, "__name__", "") or ""
        name_lower = tool_name.lower()
        # Remediation pushes fixes to a target repo — never a source fetch. Allow it.
        if any(w in name_lower for w in _REMEDIATION_WRITE_SUBSTRINGS):
            return None
        if not any(sub in name_lower for sub in _FORBIDDEN_SUBSTRINGS_WHEN_ZIP):
            return None

        target = zip_path or source_artifact_path
        logger.warning(
            "BLOCKED tool '%s' — local source available at %s; agent must use parse_uploaded_files instead.",
            tool_name,
            target,
        )
        return {
            "status": "error",
            "error": "FORBIDDEN_TOOL_FOR_UPLOAD",
            "message": (
                f"User provided local source at `{target}`. The tool "
                f"`{tool_name}` is BLOCKED for this session. You MUST call "
                f'`parse_uploaded_files(file_paths=["{target}"])` and '
                "proceed with the extracted source. Do NOT call any "
                "github_* / bitbucket_* / repository-fetch tool."
            ),
            "required_tool": "parse_uploaded_files",
            "required_args": {"file_paths": [target]},
        }
    except Exception as e:
        logger.debug(f"block_github_when_zip_uploaded skipped: {e}")
    return None


_SEARCH_TOOL_SUBSTRINGS = (
    "search_code",
    "search_repositor",
    "search_user",
    "search_issue",
)


def block_github_wrong_repo(tool, args, tool_context):
    """HARD GUARD: reject GitHub calls targeting a repo other than the authorized one.

    When the user provides a GitHub URL, constitution_callback extracts the owner/repo
    and stores them in state. This guard enforces that every subsequent GitHub tool call
    uses exactly that owner/repo. Search tools (search_code, search_repositories, etc.)
    are blocked unconditionally when a repo is authorized because they ignore owner/repo
    scoping and can query all of GitHub.
    """
    try:
        state = getattr(tool_context, "state", None) or {}
        authorized_owner = state.get("authorized_github_owner", "")
        authorized_repo = state.get("authorized_github_repo", "")

        tool_name = (getattr(tool, "name", "") or getattr(tool, "__name__", "") or "").lower()

        if not authorized_owner or not authorized_repo:
            # No repo authorized for this session. A legitimate GitHub-sourced review
            # always populates authorized_github_owner/repo (constitution_callback
            # extracts them from the URL before the first github tool runs), and ZIP
            # uploads are handled by block_github_when_zip_uploaded above. So a
            # repo-scoped GitHub fetch or a search tool arriving here is a hallucinated
            # target (e.g. a follow-up guessing google/adk-python) — reject it and steer
            # the agent back to the saved review / remediation plan.
            call_owner = (args or {}).get("owner", "")
            call_repo = (args or {}).get("repo", "")
            is_search = any(sub in tool_name for sub in _SEARCH_TOOL_SUBSTRINGS)
            if is_search or (call_owner and call_repo):
                logger.warning(
                    "BLOCKED tool '%s' targeting %s/%s — no repository is authorized for this "
                    "session; agent must answer from the saved review/remediation plan.",
                    tool_name,
                    call_owner or "?",
                    call_repo or "?",
                )
                return {
                    "status": "error",
                    "error": "NO_AUTHORIZED_REPO",
                    "message": (
                        f"BLOCKED: no repository is authorized for this session (the review "
                        f"came from an uploaded ZIP or inline code, not a GitHub URL). The tool "
                        f"`{tool_name}` may NOT fetch or search an arbitrary repository. Answer "
                        f"from the saved review findings and the remediation plan already in "
                        f"session state; do NOT fetch, review, or name any external repository."
                    ),
                }
            return None  # Non-repo-scoped tool (no owner/repo) — let other guards handle it

        # Block search tools unconditionally — they bypass owner/repo scoping
        if any(sub in tool_name for sub in _SEARCH_TOOL_SUBSTRINGS):
            logger.warning(
                "BLOCKED search tool '%s' — search tools are forbidden; fetch specific files from %s/%s instead.",
                tool_name,
                authorized_owner,
                authorized_repo,
            )
            return {
                "status": "error",
                "error": "FORBIDDEN_SEARCH_TOOL",
                "message": (
                    f"The tool `{tool_name}` is FORBIDDEN. Search tools query all of GitHub "
                    f"and are not permitted. Fetch specific files from the authorized repo "
                    f"`{authorized_owner}/{authorized_repo}` using `github_get_multiple_files` "
                    f"or `github_get_file_contents` instead."
                ),
            }

        call_owner = (args or {}).get("owner", "")
        call_repo = (args or {}).get("repo", "")

        if not call_owner or not call_repo:
            return None  # Tool doesn't take owner/repo args — not a repo-scoped call

        if call_owner.lower() == authorized_owner.lower() and call_repo.lower() == authorized_repo.lower():
            return None  # Correct repo — allow

        logger.warning(
            "BLOCKED tool '%s' targeting %s/%s — only %s/%s is authorized for this session.",
            tool_name,
            call_owner,
            call_repo,
            authorized_owner,
            authorized_repo,
        )
        return {
            "status": "error",
            "error": "UNAUTHORIZED_REPO",
            "message": (
                f"BLOCKED: This session is authorized to analyze `{authorized_owner}/{authorized_repo}` only. "
                f"You attempted to access `{call_owner}/{call_repo}` which is NOT authorized. "
                f"Use owner=`{authorized_owner}` and repo=`{authorized_repo}` in your tool call."
            ),
        }
    except Exception as e:
        logger.debug(f"block_github_wrong_repo skipped: {e}")
    return None


# Deterministic single-shot tools: calling them more than once per invocation can
# only repeat or worsen their effect. github_apply_remediation_plan does branch +
# all commits + PR in one call, so a re-call against the same (possibly failing)
# plan is pure waste — and, because the tool reports failure via a status:"error"
# dict (never a raised exception), nothing in ADK's retry plumbing bounds the
# re-calls. This guard caps it at one call per invocation so a failing apply can't
# spin the executor into an unbounded model↔tool loop.
_CALL_ONCE_TOOLS = ("github_apply_remediation_plan",)


def block_apply_remediation_replay(tool, args, tool_context):
    """HARD GUARD: allow a deterministic single-shot tool at most once per invocation.

    On the first call we mark a temp flag and let it run. Any later call to the same
    tool short-circuits with a terminal result (returning a dict from a
    before_tool_callback skips the underlying tool), so the executor LLM sees a
    definitive answer and emits its final response instead of re-calling forever.
    """
    try:
        tool_name = (getattr(tool, "name", "") or getattr(tool, "__name__", "") or "").lower()
        if not any(t in tool_name for t in _CALL_ONCE_TOOLS):
            return None

        state = getattr(tool_context, "state", None)
        if state is None:
            return None

        flag_key = "temp:apply_remediation_called"
        if state.get(flag_key):
            logger.warning(
                "BLOCKED repeat call to '%s' — deterministic apply already ran once this "
                "invocation; refusing to re-execute.",
                tool_name,
            )
            # Escalate the flag so _executor_after_callback can detect the loop.
            state["temp:apply_remediation_looped"] = True
            return {
                "status": "terminal",
                "error": "APPLY_ALREADY_RAN",
                "message": (
                    f"`{tool_name}` already ran once and the result is recorded. "
                    "YOUR TURN IS COMPLETE. Do NOT call any tool again. "
                    "Emit only a plain-text summary of the previous call's outcome and stop immediately."
                ),
            }

        state[flag_key] = True
    except Exception as e:
        logger.debug(f"block_apply_remediation_replay skipped: {e}")
    return None


def block_github_misuse(tool, args, tool_context):
    """Combined guard: blocks GitHub misuse for both ZIP uploads and wrong repos,
    and caps deterministic single-shot tools at one call per invocation.

    Runs block_github_when_zip_uploaded first (upload takes precedence),
    then block_github_wrong_repo (repo-scoping enforcement), then
    block_apply_remediation_replay (single-shot cap).
    """
    result = block_github_when_zip_uploaded(tool, args, tool_context)
    if result is not None:
        return result
    result = block_github_wrong_repo(tool, args, tool_context)
    if result is not None:
        return result
    return block_apply_remediation_replay(tool, args, tool_context)
