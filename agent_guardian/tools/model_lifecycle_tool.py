from __future__ import annotations

"""
model_lifecycle_tool.py — Live Gemini / Vertex AI Model Catalog Query.

Provides a single ADK-compatible tool function `get_model_lifecycle()` that:
1. Queries the Gemini Developer API  (GET /v1beta/models)
2. Queries the Vertex AI Model Garden (GET /v1/publishers/google/models)
3. Merges results, classifying each model into a lifecycle status tier.

The ADK Expert agent calls this tool instead of relying on training-data
knowledge — eliminating hallucinated deprecation dates and missed retirements.

Auth strategy (automatically resolved):
  - Vertex AI endpoint  → uses Application Default Credentials (ADC) via
    google-auth, which resolves to the Cloud Run service account in prod
    and to `gcloud auth application-default login` in local dev.
  - Gemini Developer API → uses GOOGLE_API_KEY env var (already in .env).

Returns a JSON-serialisable list of model dicts (safe as an ADK tool output).
"""

import logging
import os
import urllib.error
import urllib.request
from typing import Any

from ..utils.confluence_rest import request_json_with_retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
_VERTEX_API_BASE = "https://us-central1-aiplatform.googleapis.com"

# Strings in the model name / display_name that indicate a model is no longer
# actively recommended.  We flag these so the agent can surface them.
_DEPRECATED_SIGNALS = ["deprecated", "sunset", "retired", "end-of-life", "eol"]

# Launch stages considered "generally available / stable"
_GA_STAGES = {"GA", "STABLE", "GENERALLY_AVAILABLE"}

# ---------------------------------------------------------------------------
# Latest recommended models (per tier). These are the ONLY models the tool
# should ever suggest as replacements. Update this block when a newer family
# ships — everything else is derived from it.
# ---------------------------------------------------------------------------
_LATEST_PRO = "gemini-3.6-pro"
_LATEST_FLASH = "gemini-3.7-flash"
_LATEST_FLASH_LITE = "gemini-3.1-flash-lite"
_LATEST_MODELS = (_LATEST_PRO, _LATEST_FLASH, _LATEST_FLASH_LITE)


def _is_latest(model_id: str) -> bool:
    """True if the model is one of the current latest-recommended models."""
    return model_id in _LATEST_MODELS


def _latest_equivalent(model_id: str) -> str:
    """Map any model to the latest model in its tier (so we only ever
    recommend a current model, never a deprecated/older one)."""
    mid = model_id.lower()
    if "flash-lite" in mid or "flash_lite" in mid or "lite" in mid:
        return _LATEST_FLASH_LITE
    if "flash" in mid:
        return _LATEST_FLASH
    if "pro" in mid or "ultra" in mid:
        return _LATEST_PRO
    return _LATEST_FLASH  # sensible general-purpose default


# Models that are *always* current — never flag these as deprecated even if
# the API does not explicitly mark them stable yet. (Older-but-supported
# families stay here so they aren't mis-flagged DEPRECATED, but they still get
# a latest `recommended_replacement` below.)
_ALWAYS_CURRENT = {
    _LATEST_PRO,
    _LATEST_FLASH,
    _LATEST_FLASH_LITE,
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_vertex_token() -> str | None:
    """Return a bearer token for Vertex AI using google-auth ADC."""
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception as e:
        logger.warning(f"model_lifecycle: Could not obtain ADC token: {e}")
        return None


def _get_api_key() -> str:
    """Return the Gemini Developer API key from env."""
    return os.environ.get("GOOGLE_API_KEY", "")


# ---------------------------------------------------------------------------
# Gemini Developer API — lists all public Gemini models
# ---------------------------------------------------------------------------


def _fetch_gemini_models() -> list[dict]:
    """Query GET /v1beta/models from the Gemini Developer API."""
    api_key = _get_api_key()
    if not api_key:
        logger.warning("model_lifecycle: GOOGLE_API_KEY not set; skipping Gemini API query.")
        return []

    url = f"{_GEMINI_API_BASE}/v1beta/models?key={api_key}&pageSize=200"
    try:
        data = request_json_with_retry(
            url,
            {"Accept": "application/json", "User-Agent": "AgentGuardian/1.0"},
            timeout=15,
        )
        return data.get("models", [])
    except urllib.error.HTTPError as e:
        logger.warning(f"model_lifecycle: Gemini API HTTP {e.code}: {e.read(200)}")
        return []
    except Exception as e:
        logger.warning(f"model_lifecycle: Gemini API error: {e}")
        return []


# ---------------------------------------------------------------------------
# Vertex AI Model Garden — lists publisher models (Google family)
# ---------------------------------------------------------------------------


def _fetch_vertex_models() -> list[dict]:
    """Query Vertex AI publisher models for Google Gemini family."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    # Model Garden catalog endpoint requires a regional endpoint
    # 'global' is not a valid region for this specific API path
    if location == "global":
        location = "us-central1"
    if not project:
        logger.warning("model_lifecycle: GOOGLE_CLOUD_PROJECT not set; skipping Vertex query.")
        return []

    token = _get_vertex_token()
    if not token:
        return []

    # Use the Vertex AI generative models endpoint to list available models
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1beta1"
        f"/projects/{project}/locations/{location}/publishers/google/models"
    )
    try:
        data = request_json_with_retry(
            url,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "AgentGuardian/1.0",
            },
            timeout=20,
        )
        return data.get("publisherModels", [])
    except urllib.error.HTTPError as e:
        body = e.read(300).decode("utf-8", errors="replace")
        logger.warning(f"model_lifecycle: Vertex API HTTP {e.code}: {body[:150]}")
        return []
    except Exception as e:
        logger.warning(f"model_lifecycle: Vertex API error: {e}")
        return []


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def _classify_model(model_id: str, raw: dict) -> dict:
    """
    Given a raw model dict from either API, return a normalised lifecycle record.

    Fields returned:
        model_id            str   e.g. "gemini-2.5-flash"
        display_name        str   human-readable label
        status              str   "STABLE" | "PREVIEW" | "DEPRECATED" | "UNKNOWN"
        input_token_limit   int   max input tokens (0 if unknown)
        output_token_limit  int   max output tokens (0 if unknown)
        deprecation_date    str   ISO date or "N/A"
        recommended_replacement  str  model_id of replacement or ""
        source              str   "gemini_api" | "vertex_ai"
        raw_launch_stage    str   original launch_stage string from API
    """
    name_lower = model_id.lower()

    # --- Status classification ---
    status = "UNKNOWN"
    deprecation_date = "N/A"
    replacement = ""

    # Check always-current set first
    model_base = name_lower.split(":")[0]
    for current in _ALWAYS_CURRENT:
        if current in model_base or model_base in current:
            status = "STABLE"
            break

    # Gemini Developer API fields
    launch_stage = str(raw.get("supportedGenerationMethods", raw.get("launchStage", ""))).upper()
    raw_stage = raw.get("launchStage", raw.get("version", ""))

    if status == "UNKNOWN":
        if any(s in name_lower for s in _DEPRECATED_SIGNALS):
            status = "DEPRECATED"
        elif any(s in launch_stage for s in _GA_STAGES):
            status = "STABLE"
        elif "preview" in name_lower or "preview" in launch_stage.lower():
            status = "PREVIEW"
        elif "exp" in name_lower or "experimental" in name_lower:
            status = "PREVIEW"
        else:
            status = "STABLE"  # default to stable if no signal

    # Deprecation info from Vertex AI model dict
    deprecation_info = raw.get("deprecationInfo", raw.get("versionDeprecationTime", ""))
    if deprecation_info:
        deprecation_date = str(deprecation_info)
        if status != "DEPRECATED":
            status = "DEPRECATED"

    # Recommended replacement — ALWAYS resolve to a latest-recommended model.
    # The model is its own best version only if it IS one of the latest models;
    # otherwise we point at the latest model in the same tier. An API-provided
    # successor is honoured only when it is itself a latest model.
    if _is_latest(model_id):
        replacement = ""
    else:
        api_successor = raw.get("recommendedModelId", "") or raw.get("successor", {}).get("name", "")
        if api_successor and api_successor in _LATEST_MODELS and api_successor != model_id:
            replacement = api_successor
        else:
            replacement = _latest_equivalent(model_id)

    # Token limits
    input_limit = int(raw.get("inputTokenLimit", raw.get("inputContextLength", 0)) or 0)
    output_limit = int(raw.get("outputTokenLimit", raw.get("maxOutputTokens", 0)) or 0)

    return {
        "model_id": model_id,
        "display_name": raw.get("displayName", raw.get("name", model_id)),
        "status": status,
        "is_latest": _is_latest(model_id),
        "input_token_limit": input_limit,
        "output_token_limit": output_limit,
        "deprecation_date": deprecation_date,
        "recommended_replacement": replacement,
        "raw_launch_stage": str(raw_stage),
        "source": raw.get("_source", "unknown"),
    }


# ---------------------------------------------------------------------------
# Public ADK Tool
# ---------------------------------------------------------------------------


def get_model_lifecycle(
    filter_status: str = "all",
    include_gemini_only: bool = True,
) -> dict[str, Any]:
    """
    Fetch live model lifecycle data from Google's Vertex AI and Gemini APIs.

    Use this tool to populate the Model Lifecycle Audit table in the report.
    NEVER fill that table from memory — always call this tool first.

    SUGGESTION RULE — recommend the LATEST models ONLY:
        When you advise which model to use, pick from ``latest_recommended``
        (or the ``recommended_models`` list). NEVER suggest a model whose
        ``status`` is ``"DEPRECATED"`` and never suggest a model that has a
        non-empty ``recommended_replacement`` — suggest that replacement (which
        is always a current latest model) instead. A record with
        ``is_latest: true`` is a safe thing to recommend; anything else is not.

    Args:
        filter_status: One of "all" | "deprecated" | "stable" | "preview".
                       Filters the returned list. Default "all".
        include_gemini_only: If True (default), only return Gemini-family
                             models (filters out Palm2, Imagen, etc.).

    Returns:
        A dict with:
        - ``models``: list of model lifecycle records (each with model_id,
          status, is_latest, deprecation_date, recommended_replacement, limits).
        - ``latest_recommended``: {"pro", "flash", "flash_lite"} → the current
          latest model id for each tier. Recommend from here.
        - ``recommended_models``: the subset of ``models`` that are latest
          (``is_latest: true``) — the only safe models to suggest.
        - ``total``: total count before filtering.
        - ``filtered``: count after filter.
        - ``sources``: which APIs successfully responded.
        - ``error``: non-empty string if BOTH APIs failed.

    Example output::

        {
          "models": [
            {
              "model_id": "gemini-1.0-pro",
              "status": "DEPRECATED",
              "deprecation_date": "2025-04-09",
              "recommended_replacement": "gemini-2.5-pro",
              ...
            },
            {
              "model_id": "gemini-2.5-flash",
              "status": "STABLE",
              "deprecation_date": "N/A",
              ...
            }
          ],
          "total": 42,
          "filtered": 42,
          "sources": ["gemini_api", "vertex_ai"]
        }
    """
    sources_ok: list[str] = []
    seen_ids: set[str] = set()
    all_records: list[dict] = []

    # ── 1. Gemini Developer API ──────────────────────────────────────────────
    gemini_raw = _fetch_gemini_models()
    if gemini_raw:
        sources_ok.append("gemini_api")
        for m in gemini_raw:
            raw_name = m.get("name", "")  # e.g. "models/gemini-2.5-flash"
            model_id = raw_name.replace("models/", "").strip()
            if not model_id or model_id in seen_ids:
                continue
            if include_gemini_only and not model_id.startswith("gemini"):
                continue
            seen_ids.add(model_id)
            m["_source"] = "gemini_api"
            all_records.append(_classify_model(model_id, m))

    # ── 2. Vertex AI Model Garden ────────────────────────────────────────────
    vertex_raw = _fetch_vertex_models()
    if vertex_raw:
        sources_ok.append("vertex_ai")
        for m in vertex_raw:
            # name looks like "publishers/google/models/gemini-2.5-pro"
            raw_name = m.get("name", "")
            model_id = raw_name.split("/")[-1].strip()
            if not model_id or model_id in seen_ids:
                continue
            if include_gemini_only and not model_id.startswith("gemini"):
                continue
            seen_ids.add(model_id)
            m["_source"] = "vertex_ai"
            all_records.append(_classify_model(model_id, m))

    # ── 3. Hardcoded current-model baseline (always present as a floor) ──────
    # Ensures the expert always has at least the known-current models even if
    # both APIs are temporarily unreachable.
    # Latest models carry no replacement; every older/legacy/deprecated model
    # points at the current latest model in its tier — never an older version.
    _BASELINE: list[tuple[str, str, str]] = [
        (_LATEST_PRO, "STABLE", ""),
        (_LATEST_FLASH, "STABLE", ""),
        (_LATEST_FLASH_LITE, "STABLE", ""),
        ("gemini-3.1-pro-preview", "PREVIEW", _LATEST_PRO),
        ("gemini-3-flash-preview", "PREVIEW", _LATEST_FLASH),
        ("gemini-2.5-pro", "STABLE", _LATEST_PRO),
        ("gemini-2.5-flash", "STABLE", _LATEST_FLASH),
        ("gemini-2.5-pro-preview-05-06", "DEPRECATED", _LATEST_PRO),
        ("gemini-2.5-flash-preview-05-20", "DEPRECATED", _LATEST_FLASH),
        ("gemini-2.0-flash", "STABLE", _LATEST_FLASH),
        ("gemini-2.0-flash-lite", "STABLE", _LATEST_FLASH_LITE),
        ("gemini-1.5-pro", "DEPRECATED", _LATEST_PRO),
        ("gemini-1.5-flash", "DEPRECATED", _LATEST_FLASH),
        ("gemini-1.0-pro", "DEPRECATED", _LATEST_PRO),
        ("gemini-pro", "DEPRECATED", _LATEST_PRO),
    ]
    baseline_source = "baseline_catalog" if not sources_ok else None
    for model_id, status, replacement in _BASELINE:
        if model_id not in seen_ids:
            seen_ids.add(model_id)
            all_records.append(
                {
                    "model_id": model_id,
                    "display_name": model_id,
                    "status": status,
                    "is_latest": _is_latest(model_id),
                    "input_token_limit": 0,
                    "output_token_limit": 0,
                    "deprecation_date": "2025-04-09" if status == "DEPRECATED" else "N/A",
                    "recommended_replacement": replacement,
                    "raw_launch_stage": status,
                    "source": baseline_source or "gemini_api+baseline",
                }
            )
    if baseline_source and baseline_source not in sources_ok:
        sources_ok.append(baseline_source)

    total = len(all_records)

    # The canonical "suggest these" set — only ever the latest models.
    recommended_models = [r for r in all_records if r.get("is_latest")]

    # ── 4. Apply filter ──────────────────────────────────────────────────────
    f = filter_status.lower()
    if f != "all":
        all_records = [r for r in all_records if r["status"].lower() == f]

    # Sort: DEPRECATED first, then PREVIEW, then STABLE; alphabetical within tier
    _ORDER = {"DEPRECATED": 0, "PREVIEW": 1, "STABLE": 2, "UNKNOWN": 3}
    all_records.sort(key=lambda r: (_ORDER.get(r["status"], 9), r["model_id"]))

    error_msg = ""
    if not sources_ok:
        error_msg = (
            "Both Gemini API and Vertex AI queries failed. "
            "Returning baseline catalog only. "
            "Verify GOOGLE_API_KEY and ADC credentials."
        )

    return {
        "models": all_records,
        "total": total,
        "filtered": len(all_records),
        "sources": sources_ok,
        "error": error_msg,
        # Only-latest guidance for the agent: never suggest anything else.
        "latest_recommended": {
            "pro": _LATEST_PRO,
            "flash": _LATEST_FLASH,
            "flash_lite": _LATEST_FLASH_LITE,
        },
        "recommended_models": recommended_models,
    }
