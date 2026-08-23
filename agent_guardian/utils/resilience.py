from __future__ import annotations

"""
Pipeline resilience helpers.
=============================

The review pipeline is an ADK ``Workflow``. Its scheduler aborts the *entire*
run the moment any node finishes with an error set on its context: see
``google/adk/workflow/_workflow.py::Workflow._run_loop`` — when ``child_ctx.error``
is truthy it sets ``loop_state.error_shut_down = True`` and returns, so every
downstream node (synthesis, metrics, html, remediation) is skipped. In practice
this is why an audit "breaks after planning": one of the five expert agents that
fan out after ``planning_agent`` hits a transient model error (429 / 503 /
timeout) during the parallel burst, ends with ``ctx._error`` set, and the whole
pipeline shuts down before producing a report.

This module adds two complementary layers so the agent never breaks:

1. ``harden_node`` — attaches an ADK :class:`RetryConfig` to a node. The
   workflow's ``NodeRunner`` then retries transient failures with exponential
   backoff before giving up. Used for the single-chain / composite nodes.

2. :class:`ResilientAgent` — wraps a leaf ``LlmAgent``. It runs the inner agent
   with its own retry loop and, if every attempt still fails, writes a
   deterministic fallback to the inner agent's ``output_key`` and returns
   *normally* (no exception). Because the node never ends with ``ctx._error``,
   the workflow does not trip ``error_shut_down`` and the pipeline always
   reaches the report stage. Used for the parallel experts and the report tail.
"""

import asyncio
import functools
import logging
from typing import Any, AsyncGenerator, Callable, Optional

from typing_extensions import override

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins import BasePlugin, ReflectAndRetryToolPlugin
from google.adk.workflow import RetryConfig
from google.genai import types
from pydantic import Field

logger = logging.getLogger(__name__)

# Cap any single backoff sleep so a wrapper can't stall the pipeline for minutes.
_MAX_BACKOFF_SEC = 60.0

# ADK raises NodeInterruptedError (a BaseException) to pause a workflow for
# HITL/resume. It must NEVER be swallowed by resilience wrappers or the
# framework loses the ability to pause/resume the run. The class lives in a
# private module, so fall back to a name check if the import path moves.
try:
    from google.adk.workflow._errors import (
        NodeInterruptedError as _NodeInterruptedError,
    )
except ImportError:  # pragma: no cover - ADK internal layout changed
    _NodeInterruptedError = None


def _is_node_interrupt(exc: BaseException) -> bool:
    if _NodeInterruptedError is not None:
        return isinstance(exc, _NodeInterruptedError)
    return type(exc).__name__ == "NodeInterruptedError"


def make_retry_config(max_attempts: int = 4) -> RetryConfig:
    """Standard transient-error retry policy for workflow nodes."""
    return RetryConfig(
        max_attempts=max_attempts,
        initial_delay=2.0,
        max_delay=_MAX_BACKOFF_SEC,
        backoff_factor=2.0,
        jitter=1.0,
        exceptions=None,  # retry on any exception
    )


def harden_node(agent: Any, max_attempts: int = 4) -> Any:
    """Attach a RetryConfig so the workflow retries this node's transient failures.

    Safe to call on any BaseNode (LlmAgent, Workflow, function node wrapper).
    Returns the same object for convenient chaining.
    """
    try:
        agent.retry_config = make_retry_config(max_attempts)
    except Exception as e:  # pragma: no cover - purely defensive
        logger.warning(
            "harden_node: could not set retry_config on %s: %s",
            getattr(agent, "name", agent),
            e,
        )
    return agent


class ResilientAgent(BaseAgent):
    """Runs an inner leaf agent; degrades gracefully instead of crashing the run.

    On unrecoverable failure it writes ``fallback_state`` (and, unless already
    provided there, a fallback string to the inner agent's ``output_key``) to
    session state, then completes successfully so the workflow continues.

    The wrapper deliberately shares the inner agent's ``name`` so emitted events
    keep the expert's identity in the trace and ADK's NodeRunner still treats
    routes/actions as native to the node.
    """

    model_config = {"arbitrary_types_allowed": True}

    inner_agent: Any = None
    max_attempts: int = 3
    base_delay: float = 4.0
    fallback_text: str = ""
    fallback_state: dict = Field(default_factory=dict)

    @property
    def tools(self) -> list:
        return getattr(self.inner_agent, "tools", [])

    @property
    def canonical_model(self) -> Any:
        return getattr(self.inner_agent, "canonical_model", None)

    @property
    def model(self) -> Any:
        return getattr(self.inner_agent, "model", None)

    @property
    def output_key(self) -> Optional[str]:
        return getattr(self.inner_agent, "output_key", None)

    async def _resilient_run(self, parent_invocation_ctx: Any, node_ctx: Optional[Any]) -> AsyncGenerator[Event, None]:
        from google.adk.utils.context_utils import Aclosing

        name = getattr(self.inner_agent, "name", self.name)
        last_err: Optional[Exception] = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                async with Aclosing(self.inner_agent.run_async(parent_context=parent_invocation_ctx)) as agen:
                    async for event in agen:
                        # Mirror BaseAgent._run_impl: keep author/path attribution
                        # consistent when running as a workflow node.
                        if node_ctx is not None:
                            if event.author:
                                node_ctx.event_author = event.author
                            if not event.node_info.path and event.author == name:
                                event.node_info.path = node_ctx.node_path
                        yield event
                return  # inner agent completed successfully
            except asyncio.CancelledError:
                # Never swallow cancellation — it's needed for clean shutdown.
                raise
            except BaseException as e:  # noqa: BLE001 - resilience: contain everything else
                if _is_node_interrupt(e):
                    # Workflow pause signal (HITL/resume) — must propagate.
                    raise
                # Includes odd errors surfaced by the sandboxed code executor that
                # are not plain Exceptions, so a single expert can never abort the run.
                last_err = e
                logger.error(
                    "ResilientAgent[%s]: attempt %d/%d failed: %s",
                    name,
                    attempt,
                    self.max_attempts,
                    e,
                )
                if attempt < self.max_attempts:
                    delay = min(self.base_delay * (2 ** (attempt - 1)), _MAX_BACKOFF_SEC)
                    if _is_quota_error(e):
                        # 429s only recover with time — a 4s retry is wasted.
                        delay = max(delay, 20.0)
                    await asyncio.sleep(delay)

        # Every attempt failed — install a fallback so downstream agents continue.
        async for ev in self._emit_fallback(last_err):
            yield ev

    async def _emit_fallback(self, last_err: Optional[Exception]) -> AsyncGenerator[Event, None]:
        name = getattr(self.inner_agent, "name", self.name)
        state_delta = dict(self.fallback_state)
        output_key = getattr(self.inner_agent, "output_key", None)
        if output_key and output_key not in state_delta:
            state_delta[output_key] = self.fallback_text or (
                f"[SYSTEM_NOTE: Analysis skipped] {name} could not complete after "
                f"{self.max_attempts} attempts "
                f"({type(last_err).__name__ if last_err else 'unknown error'}). "
                "Other results remain valid."
            )
        logger.warning(
            "ResilientAgent[%s]: exhausted retries; installing fallback for keys %s.",
            name,
            list(state_delta.keys()),
        )
        yield Event(
            author=name,
            actions=EventActions(state_delta=state_delta) if state_delta else EventActions(),
        )

    @override
    async def _run_impl(self, *, ctx: Any, node_input: Any = None) -> AsyncGenerator[Event, None]:
        """Workflow-node entry point."""
        async for ev in self._resilient_run(ctx.get_invocation_context(), ctx):
            yield ev

    @override
    async def _run_async_impl(self, ctx: Any) -> AsyncGenerator[Event, None]:
        """Standard runner entry point (safety net; the workflow uses _run_impl)."""
        async for ev in self._resilient_run(ctx, None):
            yield ev


def resilient(
    inner: Any,
    *,
    max_attempts: int = 3,
    base_delay: float = 4.0,
    fallback_text: str = "",
    fallback_state: Optional[dict] = None,
) -> ResilientAgent:
    """Wrap a leaf LlmAgent so a failure degrades gracefully instead of aborting."""
    return ResilientAgent(
        name=inner.name,
        description=getattr(inner, "description", "") or "",
        inner_agent=inner,
        max_attempts=max_attempts,
        base_delay=base_delay,
        fallback_text=fallback_text,
        fallback_state=fallback_state or {},
    )


# --------------------------------------------------------------------------- #
# Global safety net (ADK Plugin) — applies to EVERY agent, model and tool call.
# --------------------------------------------------------------------------- #
_TRANSIENT_SIGNALS = (
    "429",
    "500",
    "503",
    "resource_exhausted",
    "unavailable",
    "deadline",
    "timeout",
    "timed out",
    "rate limit",
    "overloaded",
    "try again",
    "protocol",
    "connect",
    "disconnect",
    "connection",
    "eof",
    "remote",
    "http2",
    "reset",
    "closed",
)
_QUOTA_SIGNALS = ("429", "resource_exhausted", "rate limit", "quota")
_ROOT_AGENT_NAME = "root_agent"
_DEGRADED_NOTE = "[SYSTEM_NOTE: Analysis skipped]"


def _is_transient(error: BaseException) -> bool:
    s = str(error).lower()
    return any(sig in s for sig in _TRANSIENT_SIGNALS)


def _is_quota_error(error: BaseException) -> bool:
    """RPM/TPM quota exhaustion — recoverable, but only by WAITING."""
    s = str(error).lower()
    return any(sig in s for sig in _QUOTA_SIGNALS)


class GlobalResiliencePlugin(BasePlugin):
    """Last-resort, runner-wide net so a model or tool error never crashes a run.

    Registered once on the App; its hooks apply globally (ADK plugins run before
    and take precedence over agent/tool-level callbacks). This complements the
    per-node :class:`ResilientAgent` / :func:`harden_node` mechanisms:

      * ``on_model_error_callback`` — for non-root agents it lets the first few
        *transient* model errors propagate so the node-level retry loops still
        run, then returns a fallback ``LlmResponse`` to suppress the exception.
        For ``root_agent`` (which has no node-level retrier) it returns a
        fallback immediately. Either way, a model error never escapes unhandled.
      * ``on_tool_error_callback`` — always returns a structured error dict so a
        raising tool surfaces as a normal error result to the LLM instead of
        crashing the run (the ReflectAndRetryToolPlugin still retries first).
    """

    def __init__(
        self,
        name: str = "global_resilience",
        model_retries: int = 2,
        quota_retries: int = 4,
    ) -> None:
        super().__init__(name=name)
        self._model_retries = model_retries
        # Quota (429) errors recover with time, so they get more propagated
        # retries than other transients — each preceded by a real backoff wait.
        self._quota_retries = quota_retries
        # Per (invocation_id, agent_name) transient-failure counter.
        self._model_fail_counts: dict[tuple[str, str], int] = {}

    @override
    async def on_model_error_callback(
        self, *, callback_context: Any, llm_request: Any, error: Exception
    ) -> Optional[LlmResponse]:
        agent_name = getattr(callback_context, "agent_name", "") or ""
        invocation_id = getattr(callback_context, "invocation_id", "") or ""
        key = (invocation_id, agent_name)
        count = self._model_fail_counts.get(key, 0) + 1
        self._model_fail_counts[key] = count

        is_quota = _is_quota_error(error)
        if is_quota:
            # Engage the adaptive pacing_callback for every subsequent agent in
            # this run: it reads this counter and inserts inter-agent delays so
            # the parallel expert fleet stops hammering the exhausted quota.
            try:
                prev = callback_context.state.get("temp:429_retry_count", 0) or 0
                callback_context.state["temp:429_retry_count"] = max(prev, count)
            except Exception:  # state unavailable in some contexts — pacing is best-effort
                pass

        # Non-root agents have node-level retriers — let early transient errors
        # propagate so those retries (and ADK's own) still get a chance. Quota
        # errors get more headroom AND a real wait first: retrying a 429
        # immediately is guaranteed to fail again until the RPM window resets.
        retry_budget = self._quota_retries if is_quota else self._model_retries
        if agent_name != _ROOT_AGENT_NAME:
            if _is_transient(error) and count <= retry_budget:
                if is_quota:
                    delay = min(15.0 * (2 ** (count - 1)), _MAX_BACKOFF_SEC)
                    logger.warning(
                        "GlobalResiliencePlugin: 429 quota exhausted for %s (attempt %d/%d) — "
                        "waiting %.0fs before allowing retry.",
                        agent_name,
                        count,
                        retry_budget,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "GlobalResiliencePlugin: transient model error for %s (attempt %d/%d) — allowing retry: %s",
                        agent_name,
                        count,
                        retry_budget,
                        error,
                    )
                return None
            else:
                # If budget is exhausted or it is a non-transient error:
                # Let it propagate so ResilientAgent's own retry/fallback mechanism catches it!
                logger.warning(
                    "GlobalResiliencePlugin: letting error propagate for %s so ResilientAgent/harden_node handles it: %s",
                    agent_name,
                    error,
                )
                raise error

        logger.error(
            "GlobalResiliencePlugin: suppressing model error for %s after %d attempt(s): %s",
            agent_name or "agent",
            count,
            error,
        )
        text = (
            f"{_DEGRADED_NOTE} The model call for '{agent_name or 'agent'}' failed and could "
            f"not recover ({type(error).__name__}). Continuing with a degraded result."
        )
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))

    @override
    async def on_tool_error_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        error: Exception,
    ) -> Optional[dict]:
        tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", "tool")
        logger.error("GlobalResiliencePlugin: suppressing tool error in %s: %s", tool_name, error)
        return {
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
            "message": (
                f"Tool '{tool_name}' failed and was skipped. Continue the review "
                "without its result; do not retry it more than once."
            ),
        }


class ErrorAwareReflectAndRetryToolPlugin(ReflectAndRetryToolPlugin):
    """ReflectAndRetryToolPlugin that also bounds tools which signal failure via a
    ``{"status": "error"}`` dict instead of raising.

    Many of this app's tools (notably ``github_apply_remediation_plan``) never raise
    — they always return a dict, using ``status`` to report success/failure. The
    base plugin's :meth:`extract_error_from_result` returns ``None``, so those
    error-dict results are invisible to it: the per-tool failure counter never
    increments and the model can re-call a permanently-failing tool without bound.

    Overriding ``extract_error_from_result`` makes a ``status == "error"`` result
    count as a failure, so consecutive failures are capped at ``max_retries`` and
    the model receives "stop using this tool" guidance. Construct with
    ``throw_exception_if_retry_exceeded=False`` so exceeding the limit returns that
    guidance rather than raising (which would otherwise abort the run).
    """

    @override
    async def extract_error_from_result(
        self, *, tool: Any, tool_args: dict, tool_context: Any, result: Any
    ) -> Optional[dict]:
        if isinstance(result, dict):
            status = str(result.get("status", "")).lower()
            if status in {"error", "terminal"}:
                return result
        return None


def safe_callback(fn: Callable) -> Callable:
    """Wrap an agent callback so a raised exception never crashes the agent.

    Works for both sync and async callbacks: on error it logs and returns
    ``None`` (which tells ADK to proceed normally). Use on before/after agent
    callbacks whose body could raise (e.g. state setup, file interception).
    """
    import inspect

    fn_name = getattr(fn, "__name__", fn)

    def _suppress(e: Exception) -> None:
        logger.error("safe_callback: %s raised and was suppressed: %s", fn_name, e)

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _async_wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                _suppress(e)
                return None

        return _async_wrapper

    @functools.wraps(fn)
    def _sync_wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            _suppress(e)
            return None

    return _sync_wrapper
