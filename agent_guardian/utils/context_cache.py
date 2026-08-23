from __future__ import annotations

"""
ADK context caching for expert system instructions and multi-agent handoffs.

When set on App(context_cache_config=...), ADK gives each agent its own cache
across multi-agent transfers and turns, avoiding redundant re-sending of
system instructions and tool schemas.

Enabled by default (ENABLE_CONTEXT_CACHING=true). Can be customized or disabled
via environment variables:
- ENABLE_CONTEXT_CACHING: "true" (default) or "false"
- CONTEXT_CACHE_TTL_SECONDS: Cache time-to-live (default: 1800s / 30 mins)
- CONTEXT_CACHE_INTERVALS: Invocations before refreshing cache (default: 10)
- CONTEXT_CACHE_MIN_TOKENS: Minimum token count before caching (default: 0)
"""

import logging
import os

logger = logging.getLogger(__name__)


def _is_caching_enabled() -> bool:
    val = os.getenv("ENABLE_CONTEXT_CACHING", "true").strip().lower()
    return val in ("1", "true", "yes", "on")


def get_cache_config():
    """Return a ContextCacheConfig if caching is enabled, else None.

    When present on an App or LlmAgent, ADK uses context caching for repeated turns
    and agent handoffs.
    """
    if not _is_caching_enabled():
        logger.debug("context_cache: disabled via ENABLE_CONTEXT_CACHING")
        return None
    try:
        from google.adk.agents.context_cache_config import ContextCacheConfig

        ttl_seconds = int(os.getenv("CONTEXT_CACHE_TTL_SECONDS", "1800"))
        cache_intervals = int(os.getenv("CONTEXT_CACHE_INTERVALS", "10"))
        min_tokens = int(os.getenv("CONTEXT_CACHE_MIN_TOKENS", "0"))

        logger.debug(
            "context_cache: enabled (ttl=%ds, intervals=%d, min_tokens=%d)",
            ttl_seconds,
            cache_intervals,
            min_tokens,
        )
        return ContextCacheConfig(
            ttl_seconds=ttl_seconds,
            cache_intervals=cache_intervals,
            min_tokens=min_tokens,
        )
    except ImportError:
        logger.warning(
            "context_cache: ContextCacheConfig is not available in this ADK version. Caching disabled."
        )
        return None
    except Exception as err:
        logger.warning("context_cache: failed to initialize ContextCacheConfig: %s", err)
        return None

