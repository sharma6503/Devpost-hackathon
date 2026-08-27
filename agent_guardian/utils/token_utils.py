from __future__ import annotations

"""
Token Management Utilities for Gemini.
Provides precise token counting using the google-genai SDK to prevent
context window saturation and quota errors.
"""

import logging
import os
from typing import Any, Union, List
from google.genai import Client, types
from ..config import Config, _env_int

logger = logging.getLogger(__name__)
_cfg = Config()


class TokenManager:
    """
    Helper to count tokens precisely for Gemini models.
    Falls back to character-based estimation if the API is unavailable.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or _cfg.agent_settings.expert_model
        self._client = None
        self._auth_failed = False
        self._init_client()

    def _init_client(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        use_vertex = (
            os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "0").lower() in ("1", "true")
            or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "0").lower() in ("1", "true")
        )
        project = (
            os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID") or os.environ.get("PROJECT_ID")
        )
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        try:
            if use_vertex and project:
                self._client = Client(vertexai=True, project=project, location=location)
                logger.debug(f"TokenManager: Initialized Vertex AI client ({project}/{location})")
            elif api_key:
                self._client = Client(api_key=api_key)
                logger.debug("TokenManager: Initialized Google AI client.")
        except Exception as e:
            logger.debug(f"TokenManager: Failed to init GenAI client: {e}")

    def reset(self) -> None:
        """Clear latched auth-failure flag so a new review re-tries the API."""
        self._auth_failed = False
        if self._client is None:
            self._init_client()

    def count_tokens(self, text: Union[str, List[str]]) -> int:
        """Counts tokens in the provided text using the Gemini API."""
        if not text:
            return 0

        input_text = text if isinstance(text, str) else "\n".join(text)

        if self._client and not self._auth_failed:
            try:
                response = self._client.models.count_tokens(model=self.model_name, contents=[input_text])
                return response.total_tokens
            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or "unauthorized" in err_str or "permission" in err_str:
                    if not self._auth_failed:
                        logger.warning(
                            f"TokenManager: Auth failure on {self.model_name}. Falling back to heuristic. Error: {e}"
                        )
                        self._auth_failed = True
                else:
                    logger.debug(f"TokenManager: API count failed ({e}). Using heuristic.")

        return len(input_text) // 3  # code heuristic

    def is_over_budget(self, text: str, budget: int) -> bool:
        """Checks if the text exceeds a specific token budget."""
        return self.count_tokens(text) > budget

    def truncate_to_budget(self, parts: List[str], token_budget: int) -> str:
        """
        Truncates a list of strings to fit within a token budget.
        Now used primarily for the CODEBASE injection, not for audit findings.
        """
        if not parts:
            return ""

        total_tokens = 0
        accepted_parts = []

        for part in parts:
            part_tokens = self.count_tokens(part)
            if total_tokens + part_tokens > token_budget:
                break
            accepted_parts.append(part)
            total_tokens += part_tokens

        # Defensive: if still over budget (rare, e.g. token heuristic underestimates), trim from end
        while self.count_tokens("\n\n".join(accepted_parts)) > token_budget and accepted_parts:
            accepted_parts.pop()
        return "\n\n".join(accepted_parts)


# Global instances
expert_token_manager = TokenManager(_cfg.agent_settings.expert_model)
synthesis_token_manager = TokenManager(_cfg.agent_settings.synthesis_model)

from google.adk.agents.callback_context import CallbackContext
from google.adk.plugins import BasePlugin


async def synthesis_budget_callback(callback_context: CallbackContext):
    """
    Universal budget-protection callback for agents that inject many state keys.
    Prevents 400 INVALID_ARGUMENT crashes in aggregators (synthesis, evaluation, html).

    Enforces a HARD aggregate budget by progressively shrinking the per-key cap
    until the total stays under the limit. This guarantees we never blow the
    1M-token Gemini ceiling regardless of how many large state keys are injected.
    """
    # Keys that often contain massive data
    HIGH_CONTEXT_KEYS = [
        "raw_codebase",
        "code_logic",
        "code_config",
        "code_docs",
        "confluence_rules",
        "confluence_page_body",
        "adk_review_result",
        "quality_review_result",
        "security_review_result",
        "governance_review_result",
        "validation_result",
        "security_domain_report",
        "quality_domain_report",
        "technical_domain_report",
        "failing_review_content",
        "evaluation_result",
        # Per-page Confluence state keys (long names)
        "constitution",
    ]

    # Hard ceiling for the SUM of all injected high-context keys.
    # 800k chars ≈ 200–280k tokens for code/text — safe under 1M token limit
    # once you add prompt scaffolding and conversation history.
    MAX_TOTAL_INJECTED_CHARS = min(_cfg.max_codebase_chars, 800_000)

    total_chars = 0
    sizes = {}
    for key in HIGH_CONTEXT_KEYS:
        val = callback_context.state.get(key)
        if isinstance(val, str) and val:
            sizes[key] = len(val)
            total_chars += len(val)

    if total_chars <= MAX_TOTAL_INJECTED_CHARS or not sizes:
        return

    logger.warning(
        f"Synthesis budget exceeded ({total_chars} > {MAX_TOTAL_INJECTED_CHARS}). Applying iterative truncation."
    )

    # Find the mathematically optimal per-key cap using Binary Search
    low = 0
    high = max(sizes.values())
    opt_cap = 0
    while low <= high:
        mid = (low + high) // 2
        current_sum = sum(min(size, mid) for size in sizes.values())
        if current_sum <= MAX_TOTAL_INJECTED_CHARS:
            opt_cap = mid
            low = mid + 1
        else:
            high = mid - 1

    # Apply the optimal cap to truncate oversized keys while preserving canonical full content
    for key, size in list(sizes.items()):
        if size > opt_cap:
            val = callback_context.state.get(key)
            if isinstance(val, str):
                canonical_key = f"_canonical_{key}"
                if canonical_key not in callback_context.state:
                    callback_context.state[canonical_key] = val
                callback_context.state[key] = val[:opt_cap] + "\n\n[TRUNCATED BY SYNTHESIS_BUDGET_CALLBACK]"
                sizes[key] = opt_cap

    new_total = sum(sizes.values())
    logger.info(f"Truncated injected state to {new_total} chars (per-key cap={opt_cap}). Preserved canonical copies in state.")


def get_canonical_state(state: Any, key: str) -> Any:
    """Retrieve the un-truncated canonical value for a state key if preserved,
    otherwise returns state.get(key)."""
    if state is None:
        return None
    canonical_key = f"_canonical_{key}"
    if hasattr(state, "get"):
        return state.get(canonical_key) or state.get(key)
    return None


def _measure_part(part) -> int:
    if getattr(part, "text", None):
        return len(part.text)
    inline = getattr(part, "inline_data", None)
    if inline is not None and getattr(inline, "data", None) is not None:
        try:
            return len(inline.data)
        except Exception:
            return 0
    fn_resp = getattr(part, "function_response", None)
    if fn_resp is not None:
        try:
            resp = fn_resp.response
            if isinstance(resp, str):
                return len(resp)
            if isinstance(resp, dict):
                # Sum string-valued fields (most tool payloads put bulk data in strings)
                return sum(len(v) for v in resp.values() if isinstance(v, str))
        except Exception:
            return 0
    return 0


def _measure_contents(contents) -> int:
    total = 0
    for msg in contents or []:
        for part in getattr(msg, "parts", None) or []:
            total += _measure_part(part)
    return total


def _truncate_function_response(fn_resp, cap: int) -> bool:
    """Truncate large string fields in a tool response. Returns True if changed."""
    try:
        resp = fn_resp.response
        if isinstance(resp, str):
            if len(resp) > cap:
                fn_resp.response = resp[:cap] + "\n\n[PRUNED BY TOKEN_SAFETY_PLUGIN]"
                return True
        elif isinstance(resp, dict):
            changed = False
            for k, v in list(resp.items()):
                if isinstance(v, str) and len(v) > cap:
                    resp[k] = v[:cap] + "\n\n[PRUNED BY TOKEN_SAFETY_PLUGIN]"
                    changed = True
            return changed
    except Exception as e:
        logger.debug(f"_truncate_function_response: skipped malformed response: {e}")
        return False
    return False


def prune_massive_history(contents: List[types.Content], limit_chars: int = 1_200_000):
    """
    Aggressively prunes large message/tool parts BEFORE they are sent to Gemini.
    Enforces a HARD total character budget by iteratively lowering the per-part
    cap until the aggregate fits under `limit_chars`.

    Default `limit_chars` is 1.2M characters which maps to roughly 300-400k
    tokens for mixed code/text — a safe margin under Gemini's 1,048,576 input
    token limit.
    """
    if not contents:
        return

    total_chars = _measure_contents(contents)
    if total_chars <= limit_chars:
        return

    logger.warning(f"History too large ({total_chars} chars > {limit_chars}). Applying aggressive part-level pruning.")

    # Iteratively shrink the per-part cap until total fits the budget.
    for part_cap in (50_000, 25_000, 12_000, 6_000, 3_000, 1_500):
        for msg in contents:
            for part in getattr(msg, "parts", None) or []:
                if getattr(part, "text", None) and len(part.text) > part_cap:
                    part.text = part.text[:part_cap] + "\n\n[PRUNED BY TOKEN_SAFETY_PLUGIN]"
                fn_resp = getattr(part, "function_response", None)
                if fn_resp is not None:
                    _truncate_function_response(fn_resp, part_cap)
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None) is not None:
                    try:
                        if len(inline.data) > part_cap:
                            # Drop binary payloads — they're unusable as text context anyway
                            inline.data = b""
                    except Exception as e:
                        logger.debug(f"prune_massive_history: could not drop inline_data: {e}")

        new_total = _measure_contents(contents)
        if new_total <= limit_chars:
            logger.info(f"Pruned history to {new_total} chars (cap={part_cap}, target={limit_chars}).")
            return

    logger.error(
        f"prune_massive_history: could not reduce below {limit_chars} chars "
        f"(final size={_measure_contents(contents)}). Request may still fail."
    )


def _truncate_system_instruction(llm_request, limit_chars: int):
    """Truncate the system instruction if present and oversized."""
    sys_inst = getattr(llm_request, "config", None)
    sys_inst = getattr(sys_inst, "system_instruction", None) if sys_inst else None
    if sys_inst is None:
        # Some ADK builds expose it directly
        sys_inst = getattr(llm_request, "system_instruction", None)
    if sys_inst is None:
        return

    # system_instruction can be a string or a Content
    if isinstance(sys_inst, str):
        if len(sys_inst) > limit_chars:
            new_val = sys_inst[:limit_chars] + "\n\n[PRUNED BY TOKEN_SAFETY_PLUGIN]"
            try:
                llm_request.config.system_instruction = new_val
            except Exception:
                try:
                    llm_request.system_instruction = new_val
                except Exception as e:
                    logger.warning(
                        f"TokenSafetyPlugin: could not write truncated system_instruction back to request: {e}"
                    )
            logger.warning(f"Truncated system_instruction from {len(sys_inst)} to {limit_chars} chars.")
    else:
        for part in getattr(sys_inst, "parts", None) or []:
            if getattr(part, "text", None) and len(part.text) > limit_chars:
                logger.warning(f"Truncated system_instruction part from {len(part.text)} to {limit_chars} chars.")
                part.text = part.text[:limit_chars] + "\n\n[PRUNED BY TOKEN_SAFETY_PLUGIN]"


class TokenSafetyPlugin(BasePlugin):
    """
    Global safety guard that intercepts EVERY model call to ensure
    token limits are never exceeded.

    Hard cap: ~1.2M chars total (≈ 300–400k tokens for code/text), well below
    Gemini's 1,048,576 input token limit.
    """

    # Tunable via env var TOKEN_SAFETY_LIMIT_CHARS
    DEFAULT_LIMIT_CHARS = _env_int("TOKEN_SAFETY_LIMIT_CHARS", 1_200_000)
    SYSTEM_INSTRUCTION_CAP = _env_int("TOKEN_SAFETY_SYSINSTR_CAP", 400_000)

    # Gemini accepts only a small set of inline_data MIME types. Anything else
    # (notably Windows' application/x-zip-compressed for uploaded ZIPs) triggers
    # a 400 INVALID_ARGUMENT before the request even reaches the model.
    _SUPPORTED_INLINE_MIME_PREFIXES = (
        "text/",
        "image/",
        "audio/",
        "video/",
    )
    _SUPPORTED_INLINE_MIME_EXACT = {
        "application/pdf",
        "application/json",
    }
    # Aliases we can safely rewrite to a Gemini-supported equivalent.
    _MIME_ALIASES = {
        "application/x-zip-compressed": None,  # ZIPs: drop, not viewable
        "application/zip": None,
        "application/x-tar": None,
        "application/gzip": None,
        "application/x-gzip": None,
        "application/octet-stream": None,
    }

    def __init__(self, name: str = "token_safety"):
        super().__init__(name=name)

    @classmethod
    def _sanitize_inline_data(cls, contents: Any) -> int:
        """Drop or rewrite inline_data parts whose mime_type Gemini will reject.

        Returns the number of parts removed/rewritten.
        """
        if not contents:
            return 0
        removed = 0
        for content in contents:
            parts = getattr(content, "parts", None)
            if not parts:
                continue
            kept = []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline is None:
                    kept.append(part)
                    continue
                mime = (getattr(inline, "mime_type", "") or "").lower().strip()
                # Allow if matches prefix or exact allowlist.
                if (
                    any(mime.startswith(p) for p in cls._SUPPORTED_INLINE_MIME_PREFIXES)
                    or mime in cls._SUPPORTED_INLINE_MIME_EXACT
                ):
                    kept.append(part)
                    continue
                # Try to rewrite via alias map.
                if mime in cls._MIME_ALIASES:
                    target = cls._MIME_ALIASES[mime]
                    if target is None:
                        # Drop: replace with a text breadcrumb so the model knows.
                        size_kb = len(getattr(inline, "data", b"") or b"") // 1024
                        breadcrumb_text = (
                            f"[INLINE_DATA_DROPPED] mime_type={mime!r} "
                            f"size={size_kb}KB. Use parse_uploaded_files / "
                            f"github_get_multiple_files to read its contents."
                        )
                        try:
                            kept.append(types.Part(text=breadcrumb_text))
                        except Exception:
                            # Best-effort: just drop.
                            pass
                        removed += 1
                        logger.warning(
                            f"TokenSafetyPlugin: dropped unsupported inline_data (mime_type={mime}, size={size_kb}KB)."
                        )
                        continue
                    # Rewrite mime_type in place.
                    try:
                        inline.mime_type = target
                        kept.append(part)
                        logger.info(f"TokenSafetyPlugin: rewrote inline_data mime_type {mime} -> {target}.")
                    except Exception:
                        removed += 1
                    continue
                # Unknown unsupported mime: drop with breadcrumb.
                size_kb = len(getattr(inline, "data", b"") or b"") // 1024
                try:
                    kept.append(
                        types.Part(
                            text=(
                                f"[INLINE_DATA_DROPPED] mime_type={mime!r} size={size_kb}KB (not on Gemini allowlist)."
                            )
                        )
                    )
                except Exception:
                    pass
                removed += 1
                logger.warning(
                    f"TokenSafetyPlugin: dropped inline_data with unsupported mime_type={mime!r} (size={size_kb}KB)."
                )
            # Mutate parts list in place when something changed.
            if len(kept) != len(parts):
                try:
                    content.parts = kept
                except Exception:
                    parts.clear()
                    parts.extend(kept)
        return removed

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: Any = None,
    ) -> None:
        if llm_request is None:
            return

        # 0. Sanitize inline_data MIME types (must run before token counting
        #    because Vertex rejects unsupported mimes with a 400 immediately).
        contents = getattr(llm_request, "contents", None)
        try:
            self._sanitize_inline_data(contents)
        except Exception as e:
            logger.debug(f"TokenSafetyPlugin: inline_data sanitize failed: {e}")

        # 1. Cap the system_instruction (carries injected state via {key} templates)
        try:
            _truncate_system_instruction(llm_request, self.SYSTEM_INSTRUCTION_CAP)
        except Exception as e:
            logger.debug(f"TokenSafetyPlugin: system_instruction prune failed: {e}")

        # 2. Cap conversation/tool history
        if contents:
            try:
                prune_massive_history(contents, limit_chars=self.DEFAULT_LIMIT_CHARS)
            except Exception as e:
                logger.debug(f"TokenSafetyPlugin: history prune failed: {e}")

        return None
