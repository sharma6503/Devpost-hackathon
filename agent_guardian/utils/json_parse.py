from __future__ import annotations

"""Shared JSON + Pydantic parse utility for agent after-callbacks."""

import json
import logging
import re
from typing import Type, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*|\s*```\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing ``` or ```json fences from a string."""
    return _FENCE_RE.sub("", text).strip()


def parse_json_into_model(
    raw: object,
    model_cls: Type[T],
    *,
    context: str = "",
) -> T | None:
    """Parse ``raw`` (dict, str, or fenced JSON string) into ``model_cls``.

    Returns the model instance on success, None on any failure.
    Logs the failure at ERROR level with ``context`` as a prefix.
    """
    try:
        if isinstance(raw, model_cls):
            return raw
        if isinstance(raw, dict):
            return model_cls(**raw)
        cleaned = strip_markdown_fences(str(raw))
        data = json.loads(cleaned)
        return model_cls(**data)
    except Exception as e:
        prefix = f"{context}: " if context else ""
        logger.error("%sparse failed for %s: %s", prefix, model_cls.__name__, e)
        return None
