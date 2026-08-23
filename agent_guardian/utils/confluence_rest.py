"""
confluence_rest.py — Direct Confluence REST API fetcher.

Replaces the MCP-based page fetcher with a direct REST call to
``api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api/content/{page_id}``.

This approach is more reliable in environments where ``mcp.atlassian.com``
is blocked by Cloudflare (Error 1010) or where SSE connections are not permitted
by corporate egress rules.

Auth: ATLASSIAN_USERNAME (email) + ATLASSIAN_API_TOKEN → HTTP Basic Auth.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# HTTP statuses worth retrying — rate limits and transient upstream failures.
_RETRYABLE_STATUSES = {429, 502, 503, 504}
_MAX_BACKOFF_SEC = 60.0


def request_json_with_retry(
    url: str,
    headers: dict,
    *,
    timeout: int = 30,
    attempts: int = 3,
    base_delay: float = 0.5,
) -> dict:
    """GET a JSON endpoint with exponential backoff on 429/5xx and network errors.

    Raises the final urllib error if every attempt fails — callers decide
    whether to convert that into a sentinel string or propagate.
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"URL scheme must be http or https, got {url}")

    req = urllib.request.Request(url, headers=headers)
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in _RETRYABLE_STATUSES or attempt == attempts:
                raise
            last_err = e
        except urllib.error.URLError as e:
            if attempt == attempts:
                raise
            last_err = e
        delay = min(base_delay * (2 ** (attempt - 1)), _MAX_BACKOFF_SEC)
        logger.warning(
            f"request_json_with_retry: attempt {attempt}/{attempts} failed ({last_err}); retrying in {delay:.1f}s"
        )
        time.sleep(delay)
    raise RuntimeError("unreachable")  # loop either returns or raises


async def request_json_with_retry_async(
    url: str,
    headers: dict,
    *,
    timeout: int = 30,
    attempts: int = 3,
    base_delay: float = 0.5,
) -> dict:
    """Async twin of :func:`request_json_with_retry` (httpx, non-blocking).

    Sync tools block ADK's parallel tool execution, so anything called from
    the workflow's parallel ingestion phase should use this variant.
    """
    import asyncio

    import httpx

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code in _RETRYABLE_STATUSES and attempt < attempts:
                    last_err = RuntimeError(f"HTTP {resp.status_code}")
                else:
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as e:
                if attempt == attempts:
                    raise
                last_err = e
            delay = min(base_delay * (2 ** (attempt - 1)), _MAX_BACKOFF_SEC)
            logger.warning(
                f"request_json_with_retry_async: attempt {attempt}/{attempts} "
                f"failed ({last_err}); retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")  # loop either returns or raises


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _build_basic_auth() -> str:
    """Return a Base64-encoded Basic Auth string from env vars."""
    email = os.environ.get("ATLASSIAN_USERNAME", "").strip() or os.environ.get("ATLASSIAN_EMAIL", "").strip()
    token = os.environ.get("ATLASSIAN_API_TOKEN", "").strip()
    if not email or not token:
        raise ValueError("Missing Atlassian credentials. Set ATLASSIAN_USERNAME and ATLASSIAN_API_TOKEN in .env.")
    return base64.b64encode(f"{email}:{token}".encode()).decode()


def _get_cloud_id() -> str:
    """Return the Atlassian Cloud ID from env."""
    cid = os.environ.get("ATLASSIAN_CLOUD_ID", "").strip() or os.environ.get("CONFLUENCE_CLOUD_ID", "").strip()
    if not cid:
        raise ValueError("ATLASSIAN_CLOUD_ID is not set. Run test_atlassian_auth.py to discover it.")
    return cid


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------


def fetch_confluence_page(page_id: str, *, timeout: int = 30) -> str:
    """
    Fetch a Confluence page via REST API and return its Markdown body.

    Args:
        page_id: The numeric Confluence page ID (as string).
        timeout: HTTP request timeout in seconds.

    Returns:
        Markdown string of the page content (with front-matter header),
        or an error sentinel string on failure.
    """
    req = _build_page_request(page_id)
    if isinstance(req, str):
        return req
    url, headers = req

    try:
        data = request_json_with_retry(url, headers, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read(500).decode("utf-8", errors="replace")
        logger.error(f"confluence_rest: HTTP {e.code} for page {page_id}: {body}")
        return f"[CONFLUENCE_HTTP_ERROR] page_id={page_id} status={e.code}: {body[:200]}"
    except Exception as e:
        logger.error(f"confluence_rest: Request failed for page {page_id}: {e}")
        return f"[CONFLUENCE_FETCH_ERROR] page_id={page_id}: {e}"

    return _extract_markdown(data)


def _build_page_request(page_id: str) -> tuple[str, dict] | str:
    """Return (url, headers) for a page fetch, or a sentinel string on config error."""
    try:
        cloud_id = _get_cloud_id()
        auth = _build_basic_auth()
    except ValueError as e:
        return f"[CONFLUENCE_CONFIG_ERROR] {e}"
    url = (
        f"https://api.atlassian.com/ex/confluence/{cloud_id}"
        f"/wiki/rest/api/content/{page_id}"
        f"?expand=body.storage,body.atlas_doc_format,body.view,title,space,version"
    )
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "User-Agent": "AgentGuardian/1.0",
    }
    return url, headers


async def fetch_confluence_page_async(page_id: str, *, timeout: int = 30) -> str:
    """Async variant of :func:`fetch_confluence_page` — same sentinel contract.

    Used by the workflow's parallel ingestion phase so a slow Confluence
    instance never blocks the event loop (and pages fetch concurrently).
    """
    import httpx

    req = _build_page_request(page_id)
    if isinstance(req, str):
        return req
    url, headers = req

    try:
        data = await request_json_with_retry_async(url, headers, timeout=timeout)
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500]
        logger.error(f"confluence_rest: HTTP {e.response.status_code} for page {page_id}: {body}")
        return f"[CONFLUENCE_HTTP_ERROR] page_id={page_id} status={e.response.status_code}: {body[:200]}"
    except Exception as e:
        logger.error(f"confluence_rest: Request failed for page {page_id}: {e}")
        return f"[CONFLUENCE_FETCH_ERROR] page_id={page_id}: {e}"

    return _extract_markdown(data)


def _extract_markdown(data: dict) -> str:
    """Convert a Confluence REST API content object to Markdown."""
    try:
        from confluence_agent.adf_converter import convert_adf_to_markdown

        _HAS_ADF = True
    except ImportError:
        _HAS_ADF = False

    title = data.get("title", "")
    page_id = data.get("id", "")
    space_key = data.get("space", {}).get("key", "")
    version = data.get("version", {}).get("number", "")

    front_matter = (
        f"---\ntitle: {json.dumps(title)}\npage_id: {page_id}\nspace: {space_key}\nversion: {version}\n---\n\n"
    )

    body = data.get("body", {})

    # 1. Prefer atlas_doc_format (ADF) → our converter produces best Markdown
    adf_raw = body.get("atlas_doc_format", {}).get("value", "")
    if adf_raw and _HAS_ADF:
        try:
            md = convert_adf_to_markdown(adf_raw)
            if md and md.strip():
                logger.info(f"confluence_rest: page {page_id} converted via ADF ({len(md)} chars)")
                return front_matter + md
        except Exception as e:
            logger.warning(f"confluence_rest: ADF conversion failed for {page_id}: {e}")

    # 2. Try view (HTML-ish plain text — strip tags)
    view_html = body.get("view", {}).get("value", "")
    if view_html:
        md = _strip_html(view_html)
        if md.strip():
            logger.info(f"confluence_rest: page {page_id} extracted from view HTML ({len(md)} chars)")
            return front_matter + md

    # 3. Fall back to storage (XHTML) — strip tags
    storage_html = body.get("storage", {}).get("value", "")
    if storage_html:
        md = _strip_html(storage_html)
        if md.strip():
            logger.info(f"confluence_rest: page {page_id} extracted from storage ({len(md)} chars)")
            return front_matter + md

    return f"[CONFLUENCE_EMPTY] page_id={page_id} title={title!r}"


def _strip_html(html: str) -> str:
    """Convert HTML to structured Markdown using markdownify, with a basic fallback stripper."""
    try:
        from markdownify import markdownify

        md = markdownify(html, heading_style="ATX")
        import re

        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()
    except Exception as e:
        logger.warning(f"confluence_rest: markdownify conversion failed, using basic stripper fallback: {e}")
        import re

        # Block tags → newlines
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</?(p|div|li|h[1-6]|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
        # Strip remaining tags
        html = re.sub(r"<[^>]+>", "", html)
        # Decode entities
        html = (
            html.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
            .replace("&#39;", "'")
            .replace("&quot;", '"')
        )
        # Collapse blank lines
        html = re.sub(r"\n{3,}", "\n\n", html)
        return html.strip()


# ---------------------------------------------------------------------------
# ADK-compatible tool function
# ---------------------------------------------------------------------------


def get_confluence_page(page_id: str) -> dict:
    """
    Fetch a Confluence page by its numeric page ID and return its Markdown content.

    This is an ADK function tool. The agent should call this with the page_id
    (numeric string) of the target Confluence page.

    Args:
        page_id: The numeric page ID from the Confluence URL
                 (e.g. '4922508791' from .../pages/4922508791/...).

    Returns:
        A dict with keys:
        - ``markdown``: The page content as a Markdown string.
        - ``page_id``: Echo of the requested page_id.
        - ``error``: Non-empty if the fetch failed.
    """
    content = fetch_confluence_page(page_id)
    is_error = content.startswith("[CONFLUENCE_")
    return {
        "page_id": page_id,
        "markdown": "" if is_error else content,
        "error": content if is_error else "",
        "char_count": len(content) if not is_error else 0,
    }
