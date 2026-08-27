"""
Confluence Rules Agent — Direct REST API Fetcher.

Role in Pipeline:
Runs in parallel with the `ingestion_agent` at the start of the `review_pipeline`.
It fetches live governance, risk, and compliance (GRC) standards from specified Confluence
pages using the Atlassian REST API directly (no MCP dependency).

Auth: ATLASSIAN_USERNAME + ATLASSIAN_API_TOKEN → HTTP Basic Auth (api.atlassian.com)

State Interactions:
- Reads: CONFLUENCE_PAGE_URLS, ATLASSIAN_CLOUD_ID, ATLASSIAN_USERNAME, ATLASSIAN_API_TOKEN
- Writes: `confluence_rules`, `confluence_pages_index`
"""

import asyncio
import inspect
import os
import re
import logging
from urllib.parse import unquote
from dotenv import load_dotenv

from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow, START, FunctionNode
from agent_guardian.config import Config
from agent_guardian.utils.resilience import resilient
from agent_guardian.utils.token_utils import synthesis_budget_callback

load_dotenv()

logger = logging.getLogger(__name__)
_cfg = Config()

# ---------------------------------------------------------------------------
# Parse CONFLUENCE_PAGE_URLS into per-page metadata
# ---------------------------------------------------------------------------
_CONFLUENCE_PAGE_URLS = os.environ.get("CONFLUENCE_PAGE_URLS", "")

_PAGE_URL_RE = re.compile(
    r"^(?:https?://)?(?P<host>[^/]+)/wiki/spaces/[^/]+/pages/(?P<page_id>\d+)(?:/(?P<title>[^/?#]+))?",
    re.IGNORECASE,
)


def _parse_page_urls(raw: str) -> list[dict[str, str]]:
    """Split ``CONFLUENCE_PAGE_URLS`` into structured per-page metadata."""
    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_url in [u.strip() for u in raw.split(",") if u.strip()]:
        m = _PAGE_URL_RE.match(raw_url)
        if not m:
            logger.warning(f"confluence_rules_agent: skipping unparseable URL: {raw_url}")
            continue
        page_id = m.group("page_id")
        if page_id in seen:
            continue
        seen.add(page_id)
        title_hint = unquote((m.group("title") or "").replace("+", " "))
        pages.append(
            {
                "page_id": page_id,
                "host": m.group("host"),
                "url": raw_url,
                "title_hint": title_hint,
                "state_key": f"confluence_page_{page_id}",
            }
        )
    return pages


_PAGES = _parse_page_urls(_CONFLUENCE_PAGE_URLS)
PAGE_STATE_KEYS: list[str] = [p["state_key"] for p in _PAGES]

logger.info(f"confluence_rules_agent: parsed {len(_PAGES)} Confluence page URL(s).")

# ---------------------------------------------------------------------------
# Unavailable sentinel
# ---------------------------------------------------------------------------
_UNAVAILABLE_SENTINEL = (
    "[CONFLUENCE_UNAVAILABLE] No Confluence rules fetched. "
    "Use built-in baselines and DO NOT claim Confluence validation."
)


# ---------------------------------------------------------------------------
# Direct fetch tool — used by the LlmAgent as a callable function tool
# ---------------------------------------------------------------------------


async def fetch_page_by_id(page_id: str) -> dict:
    """
    Fetch a Confluence page by its numeric ID and return structured Markdown.

    Args:
        page_id: The numeric Confluence page ID string (e.g. '4922508791').

    Returns:
        dict with keys ``markdown`` (str), ``page_id`` (str), ``error`` (str).
    """
    # Async so a slow Confluence instance never blocks ADK's event loop
    # (a sync tool stalls every other tool running in parallel).
    from agent_guardian.utils.confluence_rest import fetch_confluence_page_async

    content = await fetch_confluence_page_async(page_id)
    is_error = content.startswith("[CONFLUENCE_")
    return {
        "page_id": page_id,
        "markdown": "" if is_error else content,
        "error": content if is_error else "",
        "char_count": len(content) if not is_error else 0,
    }


# ---------------------------------------------------------------------------
# Aggregator callback
# ---------------------------------------------------------------------------


async def _aggregate_pages_func(ctx):
    """Aggregate per-page results into confluence_rules."""
    sections: list[str] = []
    available_pages: list[dict[str, str]] = []
    for page in _PAGES:
        body = ctx.state.get(page["state_key"], "") or ""
        body = body.strip()
        if not body or body.startswith("[CONFLUENCE_"):
            logger.warning(f"confluence_rules_agent: page {page['page_id']} unavailable or errored.")
            continue
        available_pages.append(page)
        title = page["title_hint"] or page["page_id"]
        m = re.search(r'^title:\s*"?([^"\n]+"?)?\s*$', body, re.MULTILINE)
        if m and m.group(1):
            title = m.group(1).strip().rstrip('"') or title
        sections.append(f"=== CONFLUENCE RULES: {title} (page_id={page['page_id']}) ===\n{body}")

    if not sections:
        ctx.state["confluence_rules"] = _UNAVAILABLE_SENTINEL
        ctx.state["confluence_pages_index"] = ""
        return

    ctx.state["confluence_rules"] = "\n\n".join(sections)
    # Note: synthesis_budget_callback is a simple utility, it doesn't need to be a node.
    # Guarded: a raising function node aborts the entire workflow run.
    try:
        await synthesis_budget_callback(ctx)
    except Exception as e:
        logger.error(f"confluence_rules_agent: budget enforcement failed (continuing): {e}")

    ctx.state["confluence_pages_index"] = "\n".join(
        f"- {p['state_key']} :: {p['title_hint'] or '(untitled)'} (pageId={p['page_id']})" for p in available_pages
    )

aggregate_pages_node = FunctionNode(name="aggregate_pages_node", func=_aggregate_pages_func)


# ---------------------------------------------------------------------------
# Per-page fetcher Agent factory
# ---------------------------------------------------------------------------


def _build_page_fetcher(page: dict[str, str]):
    """Build a single-page fetcher Agent using the direct REST API tool."""
    state_key = page["state_key"]
    instruction = f"""
You are a Confluence Page Fetcher. Your sole job is to retrieve ONE specific page.

### Target Page
- State key: `{state_key}`
- Page ID: {page["page_id"]}
- URL: {page["url"]}
- Title hint: {page["title_hint"] or "(untitled)"}

### Instructions
FIRST check if `{{{state_key}?}}` is already populated in state (it starts with `---` if valid).
- If YES and it starts with `---`: output it VERBATIM. DO NOT call any tool.
- If NO or it starts with `[CONFLUENCE_`:
  1. CALL `fetch_page_by_id` with `page_id="{page["page_id"]}"`.
  2. If the response `markdown` field is non-empty, output the `markdown` VERBATIM.
  3. If `error` is non-empty, output: `[CONFLUENCE_FETCH_ERROR] {page["page_id"]}: <error value>`

**DO NOT summarize, edit, or truncate the content.**
"""
    inner = LlmAgent(
        model=_cfg.agent_settings.ingestion_model,
        name=f"confluence_page_fetcher_{page['page_id']}",
        instruction=instruction,
        output_key=state_key,
        tools=[fetch_page_by_id],
        include_contents="none",
        disallow_transfer_to_peers=True,
        generate_content_config=_cfg.safety_config,
    )
    # Resilient wrapper: these fetchers run SEQUENTIALLY inside the composite
    # workflow, so without it one exhausted-retry failure aborts the whole
    # review. The fallback sentinel keeps the aggregate node's contract
    # (anything starting with "[CONFLUENCE_" counts as an unavailable page).
    return resilient(
        inner,
        fallback_text=(
            f"[CONFLUENCE_FETCH_ERROR] page_id={page['page_id']}: "
            "fetcher failed after retries; continuing without this page."
        ),
    )


# ---------------------------------------------------------------------------
# Lazy pre-fetch (fast path — no LLM needed)
#
# Previously this ran synchronously and sequentially AT MODULE IMPORT, so
# merely importing the package fired N blocking HTTP requests (slowing tests,
# deploys and pickling). It now runs concurrently on the first pipeline
# invocation via the async fetcher, which also stops a slow Confluence
# instance from blocking the parallel ingestion phase.
# ---------------------------------------------------------------------------


async def _prefetch_all_pages() -> bool:
    """
    Fetch the not-yet-cached pages concurrently via the REST API.
    This is the most reliable path — it avoids LLM tool-calling entirely.

    Only SUCCESSFUL fetches are cached: a transient Confluence outage on one
    run must not lock error sentinels into the module-level cache for the
    process lifetime (failed pages are retried on the next run, and the LLM
    fallback fetchers still get a chance within this run).

    Returns True if at least one page was fetched successfully.
    """
    pending = [p for p in _PAGES if p["state_key"] not in _PREFETCH_CACHE]
    if not pending:
        return bool(_PREFETCH_CACHE)

    from agent_guardian.utils.confluence_rest import fetch_confluence_page_async

    async def _fetch_one(page: dict[str, str]) -> tuple[str, str]:
        logger.info(f"confluence_rules_agent: pre-fetching page {page['page_id']} ({page['title_hint']})...")
        try:
            content = await fetch_confluence_page_async(page["page_id"])
        except Exception as e:
            content = f"[CONFLUENCE_FETCH_ERROR] {e}"
            logger.error(f"  -> EXCEPTION: {e}")
        if content.startswith("[CONFLUENCE_"):
            logger.warning(f"  -> FAILED: {content[:120]}")
        else:
            logger.info(f"  -> OK ({len(content)} chars)")
        return page["state_key"], content

    results = dict(await asyncio.gather(*(_fetch_one(p) for p in pending)))
    _PREFETCH_CACHE.update({k: v for k, v in results.items() if not v.startswith("[CONFLUENCE_")})
    return any(not v.startswith("[CONFLUENCE_") for v in _PREFETCH_CACHE.values())


# Module-level cache populated by _prefetch_all_pages()
_PREFETCH_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Callback for the pre-fetch pipeline — populates state from cache
# ---------------------------------------------------------------------------


async def _inject_prefetch_func(ctx):
    """
    Before the per-page fetcher agents run, prefetch missing pages and inject
    cached content into session state so the agents can skip tool calls.

    Never raises: a function node that errors aborts the ENTIRE workflow run
    (error_shut_down), and Confluence being down must only degrade the review.
    """
    try:
        result = _prefetch_all_pages()
        # Tolerate sync mocks in tests (e2e conftest patches this function).
        if inspect.isawaitable(result):
            await result
    except Exception as e:
        logger.error(f"confluence_rules_agent: prefetch failed; LLM fetchers will try: {e}")

    for state_key, content in _PREFETCH_CACHE.items():
        if not ctx.state.get(state_key):
            ctx.state[state_key] = content

inject_prefetch_node = FunctionNode(name="inject_prefetch_node", func=_inject_prefetch_func)


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

if _PAGES:
    # Pre-fetch happens lazily inside _inject_prefetch_callback on the first
    # pipeline run (concurrent, async) — never at import time.

    # --- Build the per-page LLM-based fetchers (fallback if pre-fetch fails) ---
    _page_fetchers = [_build_page_fetcher(p) for p in _PAGES]

    # Create a sequential edge list for the page fetchers
    _sequential_edges = []
    if _page_fetchers:
        _sequential_edges.append((START, _page_fetchers[0]))
        for i in range(len(_page_fetchers) - 1):
            _sequential_edges.append((_page_fetchers[i], _page_fetchers[i + 1]))

    _sequential_fetcher = Workflow(name="confluence_sequential_fetcher", edges=_sequential_edges)

    confluence_rules_agent = Workflow(
        name="confluence_rules_agent",
        description="Fetches Confluence GRC rules via direct REST API and aggregates them.",
        edges=[
            (START, inject_prefetch_node),
            (inject_prefetch_node, _sequential_fetcher),
            (_sequential_fetcher, aggregate_pages_node),
        ],
    )

else:
    # No pages configured — build a no-op agent that outputs the unavailable sentinel
    def _noop_tool() -> str:
        """Returns the Confluence unavailable sentinel."""
        return _UNAVAILABLE_SENTINEL

    confluence_rules_agent = LlmAgent(
        model=_cfg.agent_settings.ingestion_model,
        name="confluence_rules_agent",
        description="No-op Confluence agent (CONFLUENCE_PAGE_URLS not configured).",
        instruction=(f"No Confluence pages are configured. Output exactly: {_UNAVAILABLE_SENTINEL}"),
        output_key="confluence_rules",
        tools=[_noop_tool],
        include_contents="none",
        generate_content_config=_cfg.safety_config,
    )
