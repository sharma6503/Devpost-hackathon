from __future__ import annotations

"""
loop_state.py — Single namespaced state record for the quality-gate loop.

The loop's control state used to be scattered across three writers with two
competing exit-flag names (``_loop_exit_requested`` written by the evaluation
PASS path, ``temp:loop_exit_requested`` written by the parse-failure and
revision paths) plus a separate ``temp:revision_loop_count``. The router had to
read both flag spellings to work. All of it now lives under one ``temp:``
key (ADK clears temp-scoped state per invocation, which is exactly the loop's
lifetime).

Contract:
- evaluation/revision callbacks only record facts (request_exit, parse_failures);
- quality_gate_router is the only place that increments iterations and decides
  routing.
"""

from dataclasses import asdict, dataclass
from typing import Any

_KEY = "temp:quality_gate"


@dataclass
class LoopState:
    iterations: int = 0
    exit_requested: bool = False
    exit_reason: str = ""
    parse_failures: int = 0

    @classmethod
    def read(cls, state: Any) -> "LoopState":
        raw = state.get(_KEY)
        if not isinstance(raw, dict):
            raw = {}
        try:
            return cls(
                iterations=int(raw.get("iterations", 0) or 0),
                exit_requested=bool(raw.get("exit_requested", False)),
                exit_reason=str(raw.get("exit_reason", "")),
                parse_failures=int(raw.get("parse_failures", 0) or 0),
            )
        except (TypeError, ValueError):
            return cls()

    def write(self, state: Any) -> None:
        state[_KEY] = asdict(self)

    @classmethod
    def clear(cls, state: Any) -> None:
        """Drop the loop record so the next review starts at iteration 0.

        ADK clears ``temp:`` state per invocation, but two reviews in a single
        invocation (one user turn) share it — without this, review #2 inherits
        review #1's ``iterations`` / ``parse_failures`` and can force-exit early.
        """
        try:
            state.pop(_KEY, None)
        except Exception:
            pass

    def request_exit(self, reason: str) -> None:
        self.exit_requested = True
        self.exit_reason = reason
