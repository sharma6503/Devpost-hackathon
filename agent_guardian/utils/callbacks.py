from __future__ import annotations

"""
Callbacks for Agent Guardian pipeline execution.

Contains constitution_callback, pacing_callback, and zip file interception logic.
"""

import logging
import os
import datetime
import re as _re
from google.adk.agents.callback_context import CallbackContext
from agent_guardian.config import Config, _env_int
from agent_guardian.utils.resilience import safe_callback

logger = logging.getLogger(__name__)
configs = Config()

# Keep in sync with frontend (REMEDIATION_APPROVE_CMD / REMEDIATION_SKIP_CMD)
REMEDIATION_APPROVE_CMD = "__AG_APPROVE_REMEDIATION__"
REMEDIATION_SKIP_CMD = "__AG_SKIP_REMEDIATION__"


def parse_repo_reference(text: str) -> dict:
    """Extract ``{owner, repo, ref?}`` from a github.com or bitbucket.org URL in ``text``.

    Returns ``{}`` when no repo URL is present. ``repo`` has any trailing ``.git``
    stripped. ``ref`` is filled from a ``/tree/<ref>`` (GitHub) or ``/src/<ref>``
    (Bitbucket) path when present. Single source of truth for repo-URL parsing,
    shared by the constitution callback and remediation's target resolution.
    """
    m_gh = _re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", text)
    m_bb = _re.search(r"bitbucket\.org/([^/\s]+)/([^/\s#?]+)", text)
    stripped = text.strip().rstrip("/")
    if m_gh:
        out = {"owner": m_gh.group(1), "repo": m_gh.group(2).removesuffix(".git")}
        m_ref = _re.search(r"github\.com/[^/\s]+/[^/\s#?]+/tree/([^#?]+)", stripped)
        if m_ref:
            out["ref"] = m_ref.group(1)
        return out
    if m_bb:
        out = {"owner": m_bb.group(1), "repo": m_bb.group(2).removesuffix(".git")}
        m_ref = _re.search(r"bitbucket\.org/[^/\s]+/[^/\s#?]+/src/([^#?]+)", stripped)
        if m_ref:
            out["ref"] = m_ref.group(1)
        return out
    return {}


def _seed_default_state(callback_context: CallbackContext) -> None:
    """Populate any missing ReviewState defaults without clobbering existing keys."""
    from agent_guardian.state import ReviewState

    default_state = ReviewState().model_dump()
    for k, v in default_state.items():
        if k not in callback_context.state:
            callback_context.state[k] = v


def _inject_prompt_metadata(callback_context: CallbackContext) -> None:
    """Inject date/threshold/repo metadata and guarantee confluence defaults."""
    callback_context.state["today"] = datetime.date.today().strftime("%Y-%m-%d")
    callback_context.state["eval_pass_threshold"] = configs.agent_settings.eval_pass_threshold
    callback_context.state["default_repo"] = os.environ.get("GITHUB_REMEDIATION_REPO", "owner/repo")
    callback_context.state["base_branch"] = os.environ.get("GITHUB_BASE_BRANCH", "main")

    # Guarantee confluence_rules is never silently empty.
    if not callback_context.state.get("confluence_rules"):
        callback_context.state["confluence_rules"] = (
            "[CONFLUENCE_UNAVAILABLE] No Confluence rules fetched. "
            "Use built-in baselines and DO NOT claim Confluence validation."
        )
    if not callback_context.state.get("confluence_host_map_json"):
        callback_context.state["confluence_host_map_json"] = '{"host_to_cloud_id": {}}'


def _load_constitution(callback_context: CallbackContext) -> None:
    """Load the Code Reviewer Constitution into state (best-effort)."""
    # Since we are inside agent_guardian/utils, knowledge_base is parent's sibling
    constitution_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base", "constitution.md")
    try:
        if os.path.exists(constitution_path):
            with open(constitution_path, "r", encoding="utf-8") as f:
                callback_context.state["constitution"] = f.read()
    except Exception as e:
        logger.warning(f"Could not load constitution: {e}")


def _capture_event_horizon(callback_context: CallbackContext) -> None:
    """Record the session event count BEFORE this review adds new events."""
    try:
        _events = getattr(getattr(callback_context, "session", None), "events", None) or []
        callback_context.state["_review_event_horizon"] = len(_events)
    except Exception:
        callback_context.state["_review_event_horizon"] = 0


def _extract_repo_authorization(callback_context: CallbackContext) -> None:
    """Authorize the owner/repo/ref parsed from the user request."""
    ref = parse_repo_reference(callback_context.state.get("user_request", ""))
    if ref:
        callback_context.state["authorized_github_owner"] = ref["owner"]
        callback_context.state["authorized_github_repo"] = ref["repo"]
        if "ref" in ref:
            callback_context.state["authorized_github_ref"] = ref["ref"]


def _apply_hitl_remediation_commands(callback_context: CallbackContext) -> None:
    """Interpret human-in-the-loop remediation approve/skip/commit-id commands."""
    _cmd = callback_context.state.get("user_request", "").strip()
    if _cmd == REMEDIATION_APPROVE_CMD:
        callback_context.state["remediation_approved"] = True
        callback_context.state["remediation_skipped"] = False
        logger.info("[constitution_callback] Remediation APPROVED by user.")
    elif _cmd == REMEDIATION_SKIP_CMD:
        callback_context.state["remediation_skipped"] = True
        callback_context.state["remediation_approved"] = False
        logger.info("[constitution_callback] Remediation SKIPPED by user.")
    elif callback_context.state.get("remediation_approved") and not callback_context.state.get("remediation_commit_id"):
        if _cmd and not _cmd.startswith("__"):
            callback_context.state["remediation_commit_id"] = _cmd
            callback_context.state["remediation_status"] = "commit_id_provided"
            logger.info(f"[constitution_callback] Set remediation_commit_id = {_cmd}")


@safe_callback
async def constitution_callback(callback_context: CallbackContext):
    """Seed review state, inject prompt metadata, and capture per-turn signals.

    Thin orchestrator over the single-purpose helpers above.
    """
    _seed_default_state(callback_context)
    _inject_prompt_metadata(callback_context)
    _load_constitution(callback_context)

    # uploaded_zip_path is a CURRENT-TURN signal owned by file interception.
    callback_context.state["uploaded_zip_path"] = ""

    _capture_event_horizon(callback_context)

    # Capture original user request and detect artifacts/files.
    try:
        _apply_file_interception(callback_context)
    except Exception as e:
        logger.error(f"Error intercepting files in callback: {e}")

    _extract_repo_authorization(callback_context)
    _apply_hitl_remediation_commands(callback_context)


def _apply_file_interception(callback_context: CallbackContext):
    """Intercepts ZIP files and prepares them for ingestion."""
    from google.genai import types

    def _filter_parts_in_place(parts_list, update_state=True):
        if not parts_list:
            return
        filtered = []
        for part in parts_list:
            pre_intercepted_path = getattr(part, "_zip_path_str", None)
            if pre_intercepted_path:
                if update_state:
                    callback_context.state["uploaded_zip_path"] = pre_intercepted_path
                filtered.append(part)
                continue

            mime_type = ""
            display_name = ""
            inline_obj = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            file_obj = getattr(part, "file_data", None) or getattr(part, "fileData", None)

            if inline_obj:
                mime_type = getattr(inline_obj, "mime_type", "") or getattr(inline_obj, "mimeType", "") or ""
                display_name = getattr(inline_obj, "display_name", "") or getattr(inline_obj, "displayName", "") or ""
            elif file_obj:
                mime_type = getattr(file_obj, "mime_type", "") or getattr(file_obj, "mimeType", "") or ""
                display_name = (
                    getattr(file_obj, "display_name", "")
                    or getattr(file_obj, "displayName", "")
                    or getattr(file_obj, "file_uri", "")
                    or ""
                )

            is_zip = (
                any(x in str(mime_type).lower() for x in ["zip", "compressed", "archive", "tar", "gzip"])
                or str(display_name).lower().endswith((".zip", ".tar", ".gz", ".tgz"))
            )

            if is_zip:
                logger.info(f"Intercepting ZIP part (MIME: {mime_type}, Name: {display_name})")
                zip_path_str = ""

                if update_state:
                    data_val = None
                    if inline_obj and getattr(inline_obj, "data", None):
                        data_val = inline_obj.data
                    elif file_obj and getattr(file_obj, "data", None):
                        data_val = file_obj.data

                    if data_val:
                        try:
                            import tempfile
                            from pathlib import Path
                            import base64

                            data_bytes = data_val
                            if isinstance(data_bytes, str):
                                data_bytes = base64.b64decode(data_bytes)

                            upload_dir = Path(".adk/artifacts/uploads")
                            upload_dir.mkdir(parents=True, exist_ok=True)

                            tmp_file = tempfile.NamedTemporaryFile(dir=upload_dir, delete=False, suffix=".zip")
                            tmp_file.write(data_bytes)
                            tmp_file.flush()
                            tmp_file.close()

                            zip_path_str = str(Path(tmp_file.name).absolute())
                            callback_context.state["uploaded_zip_path"] = zip_path_str
                            logger.info(f"Preserved uploaded ZIP to `{zip_path_str}`")
                        except Exception as e:
                            logger.error(f"Failed to save ZIP data: {e}")

                msg = "[System Note: User attached a ZIP file."
                if zip_path_str:
                    msg += (
                        f" Temporarily preserved at `{zip_path_str}`."
                        " You MUST use Workflow A2 and call "
                        f'`parse_uploaded_files(file_paths=["{zip_path_str}"])`.]'
                    )
                else:
                    msg += " Already processed in a prior turn.]"

                filtered.append(types.Part.from_text(text=msg))
            else:
                filtered.append(part)

        parts_list[:] = filtered

    _cur_user_content = getattr(callback_context, "user_content", None)
    if hasattr(callback_context, "session") and getattr(callback_context.session, "events", None):
        for event in callback_context.session.events:
            event_content = getattr(event, "content", None)
            if event_content is _cur_user_content:
                continue
            if event_content and getattr(event_content, "parts", None):
                _filter_parts_in_place(event_content.parts, update_state=False)

    if hasattr(callback_context, "user_content") and callback_context.user_content:
        if getattr(callback_context.user_content, "parts", None):
            _filter_parts_in_place(callback_context.user_content.parts)
            request_parts = [p.text for p in callback_context.user_content.parts if hasattr(p, "text") and p.text]
            if request_parts:
                callback_context.state["user_request"] = "\n".join(request_parts)


@safe_callback
async def pacing_callback(callback_context: CallbackContext):
    """Adaptive pacing for quota safety."""
    import asyncio

    force_delay = _env_int("PACING_FORCE_DELAY_SEC", 0)
    base_delay = _env_int("PACING_DELAY_SEC", 12)
    retry_count = callback_context.state.get("_429_retry_count")
    if retry_count is None:
        retry_count = callback_context.state.get("temp:429_retry_count", 0)

    if retry_count > 0:
        delay = min(base_delay * (2**retry_count), 240)
        await asyncio.sleep(delay)
    elif force_delay > 0:
        await asyncio.sleep(force_delay)
