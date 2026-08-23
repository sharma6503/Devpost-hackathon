from __future__ import annotations

"""
Metrics Extractor Agent — Data Structurization & Visualization.

Role in Pipeline:
Runs after the `synthesis_agent`. Reads the raw markdown reviews from the experts
and extracts structured numerical data (issue counts, severity distribution, health scores).
Generates a base64 encoded PNG chart (using matplotlib/seaborn) to visualize the health metrics.

State Interactions:
- Reads: `security_review_result`, `governance_review_result`, `adk_review_result`, `quality_review_result`, `validation_result`
- Writes: `review_metrics` (JSON/Dict), `metrics_chart_b64`
"""

from google.adk.agents import LlmAgent
from ..config import Config
from ..prompts import METRICS_PROMPT
import json
import re
import logging

from ..utils.markdown_format import format_metrics_md

logger = logging.getLogger(__name__)
_cfg = Config()


def _extract_metrics_json(raw_str: str) -> dict:
    """
    Sanitizes and parses a JSON string from the LLM, handling markdown fences.
    """
    raw = raw_str.strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^```\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    match = re.search(r"(\{.*\})", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    return json.loads(raw)


async def generate_metrics_chart_callback(callback_context):
    """Intercept the JSON output and save to state."""
    raw_metrics = callback_context.state.get("review_metrics")
    if not raw_metrics:
        return

    # Fallback structure used when LLM output is unparseable
    _FALLBACK_METRICS: dict = {
        "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "category": {
            "adk": 0,
            "quality": 0,
            "security": 0,
            "validation": 0,
            "governance": 0,
        },
        "total": 0,
        "scores": {
            "security": 0,
            "quality": 0,
            "architecture": 0,
            "governance": 0,
            "validation": 0,
            "overall": 0,
        },
    }

    try:
        # 1. Parse JSON or handle model/dict
        if hasattr(raw_metrics, "model_dump"):
            metrics = raw_metrics.model_dump()
        elif isinstance(raw_metrics, dict):
            metrics = raw_metrics
        elif isinstance(raw_metrics, str):
            metrics = _extract_metrics_json(raw_metrics)
        else:
            metrics = _FALLBACK_METRICS

        # 2. Save to state (chart_b64 is decommissioned, set to empty for compatibility)
        callback_context.state["metrics_chart_b64"] = ""
        # Store as dict/model for interactive rendering
        callback_context.state["metrics_json"] = json.dumps(metrics)
        callback_context.state["review_metrics"] = metrics

        md_text = format_metrics_md(metrics)
        callback_context.state["review_metrics_md"] = md_text
        return None

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Metrics JSON parse failed ({e}); using fallback zero-state metrics.")
        callback_context.state["review_metrics"] = _FALLBACK_METRICS
        md_text = format_metrics_md(_FALLBACK_METRICS)
        callback_context.state["review_metrics_md"] = md_text
        return None
    except Exception as e:
        logger.error(f"Metrics processing failed unexpectedly: {e}")
        callback_context.state["review_metrics"] = _FALLBACK_METRICS
        md_text = format_metrics_md(_FALLBACK_METRICS)
        callback_context.state["review_metrics_md"] = md_text
        return None


metrics_agent = LlmAgent(
    name="metrics_agent",
    model=_cfg.agent_settings.metrics_model,
    description="Extracts multi-dimensional health metrics from review results.",
    instruction=METRICS_PROMPT,
    output_key="review_metrics",
    include_contents="none",  # LATENCY: all expert results come via state injection
    after_agent_callback=generate_metrics_chart_callback,
    # Low temperature: structured numeric extraction must be deterministic.
    generate_content_config=_cfg.generation_config(temperature=_cfg.agent_settings.metrics_temperature),
)
