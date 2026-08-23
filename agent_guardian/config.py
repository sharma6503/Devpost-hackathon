from __future__ import annotations

"""
Configuration models and settings management for Agent Guardian.

Centralizes all environment-driven configurations, model selections, safety settings,
ingestion thresholds, evaluation quality gates, and rate-limiting options using Pydantic models.
"""


import logging
import os
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    """Read an int env var; a malformed value falls back to the default
    instead of crashing the whole package at import time."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "config: env var %s=%r is not an integer; using default %d",
            name,
            raw,
            default,
        )
        return default


def _env_float(name: str, default: float) -> float:
    """Float twin of _env_int with the same fallback contract."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "config: env var %s=%r is not a number; using default %s",
            name,
            raw,
            default,
        )
        return default


class AgentSettings(BaseModel):
    """Model & identity settings for each agent tier in Agent Guardian.

    === Model Configuration & Quota Strategy ===

    Default Model:
      gemini-3.7-flash
        Confirmed capabilities: function calling, structured output, multi-turn tool use,
        code execution, reasoning, and grounding.

    QUOTA & DEPLOYMENT STRATEGY:
      gemini-3.7-flash          → Default for all agent tiers (root supervisor, expert fleet,
                                  ingestion, metrics, evaluation, synthesis, remediation, and HTML generation).
      Overridable via Env Vars → Every agent model tier can be individually customized at runtime
                                  via environment variables (e.g. ROOT_MODEL, ADK_EXPERT_MODEL, GOVERNANCE_MODEL).

    ALL environment variables are overridable at runtime.
    """

    # Root supervisor — routing only, use lightest Gemini 3 model
    root_model: str = Field(default_factory=lambda: os.environ.get("ROOT_MODEL", "gemini-3.7-flash"))
    # Ingestion — short extraction, light reasoning needed
    ingestion_model: str = Field(default_factory=lambda: os.environ.get("INGESTION_MODEL", "gemini-3.7-flash"))
    # ADK expert — deep reasoning on agent code patterns
    adk_expert_model: str = Field(default_factory=lambda: os.environ.get("ADK_EXPERT_MODEL", "gemini-3.7-flash"))
    # Quality expert — bug analysis, code smell detection
    quality_model: str = Field(default_factory=lambda: os.environ.get("QUALITY_MODEL", "gemini-3.7-flash"))
    # Security expert — threat analysis, IAM review
    security_model: str = Field(default_factory=lambda: os.environ.get("SECURITY_MODEL", "gemini-3.7-flash"))
    # Architecture expert — design pattern analysis
    # NOTE: architecture_model removed (was never read by any agent).
    # Model lifecycle is now queried live via get_model_lifecycle() tool at review time.
    # Governance — rule-matching against confluence_rules; Flash is sufficient.
    # Set GOVERNANCE_MODEL=gemini-3.1-pro-preview if the rule set needs deep
    # interpretation — Pro costs ~10x per review.
    governance_model: str = Field(default_factory=lambda: os.environ.get("GOVERNANCE_MODEL", "gemini-3.7-flash"))
    # Validator — code execution checks
    validator_model: str = Field(default_factory=lambda: os.environ.get("VALIDATOR_MODEL", "gemini-3.7-flash"))
    # Metrics — structured extraction, output_schema JSON
    metrics_model: str = Field(default_factory=lambda: os.environ.get("METRICS_MODEL", "gemini-3.7-flash"))
    # Synthesis — markdown aggregation; lite tier is sufficient
    synthesis_model: str = Field(default_factory=lambda: os.environ.get("SYNTHESIS_MODEL", "gemini-3.7-flash"))
    # HTML report — heavy structured generation (30-40 KB documents); needs
    # the full Flash tier, not lite, to avoid truncation on large reports.
    html_model: str = Field(default_factory=lambda: os.environ.get("HTML_MODEL", "gemini-3.7-flash"))
    # Legacy alias — kept for backward compatibility
    expert_model: str = Field(default_factory=lambda: os.environ.get("EXPERT_MODEL", "gemini-3.7-flash"))
    # Remediation Model & Temperature - low temperature for deterministic PR planning & tool use
    remediation_model: str = Field(default_factory=lambda: os.environ.get("REMEDIATION_MODEL", "gemini-3.7-flash"))
    remediation_temperature: float = Field(default_factory=lambda: _env_float("REMEDIATION_TEMPERATURE", 0.2))
    # Evaluation quality gate — same tier as expert fleet
    evaluation_model: str = Field(default_factory=lambda: os.environ.get("EVALUATION_MODEL", "gemini-3.7-flash"))
    # Follow-up Q&A — reasons over saved findings and selects read-only tools;
    # needs the full Flash tier (tool use + reasoning), not lite.
    followup_model: str = Field(default_factory=lambda: os.environ.get("FOLLOWUP_MODEL", "gemini-3.7-flash"))

    # Evaluation quality gate thresholds
    eval_pass_threshold: int = Field(default_factory=lambda: _env_int("EVAL_PASS_THRESHOLD", 6))
    # Default 2 — evaluate, allow one revision round for the weakest review,
    # then exit regardless of grade. Set EVAL_MAX_ITERATIONS=1 for single pass.
    eval_max_iterations: int = Field(default_factory=lambda: _env_int("EVAL_MAX_ITERATIONS", 2))

    # Per-task sampling temperatures: low for deterministic scoring/structured
    # output, higher for prose synthesis.
    evaluation_temperature: float = Field(default_factory=lambda: _env_float("EVALUATION_TEMPERATURE", 0.2))
    metrics_temperature: float = Field(default_factory=lambda: _env_float("METRICS_TEMPERATURE", 0.2))
    synthesis_temperature: float = Field(default_factory=lambda: _env_float("SYNTHESIS_TEMPERATURE", 0.7))
    html_temperature: float = Field(default_factory=lambda: _env_float("HTML_TEMPERATURE", 0.3))


class Config(BaseModel):
    """Top-level configuration container."""

    agent_settings: AgentSettings = Field(default_factory=AgentSettings)

    # GitHub / Bitbucket auth (optional — MCP falls back gracefully)
    github_token: str | None = Field(default_factory=lambda: os.environ.get("GITHUB_TOKEN"))
    github_remediation_repo: str | None = Field(default_factory=lambda: os.environ.get("GITHUB_REMEDIATION_REPO"))
    github_base_branch: str = Field(default_factory=lambda: os.environ.get("GITHUB_BASE_BRANCH", "main"))
    bitbucket_token: str | None = Field(default_factory=lambda: os.environ.get("BITBUCKET_TOKEN"))
    bitbucket_username: str | None = Field(default_factory=lambda: os.environ.get("BITBUCKET_USERNAME"))
    bitbucket_app_password: str | None = Field(default_factory=lambda: os.environ.get("BITBUCKET_APP_PASSWORD"))

    # Ingestion limits — sized to accept payloads up to 10 MB.
    # Note: the LLM context budget is enforced separately by TokenSafetyPlugin
    # and synthesis_budget_callback (see utils/token_utils.py); raising these
    # ingestion caps does NOT increase what is sent to Gemini per turn.
    max_file_size_kb: int = Field(
        default_factory=lambda: _env_int("MAX_FILE_SIZE_KB", 10240)  # 10 MB per file
    )
    max_files_per_zip: int = Field(default_factory=lambda: _env_int("MAX_FILES_PER_ZIP", 1000))
    max_total_zip_size_kb: int = Field(
        default_factory=lambda: _env_int("MAX_TOTAL_ZIP_SIZE_KB", 10240)  # 10 MB uncompressed
    )
    max_codebase_chars: int = Field(
        default_factory=lambda: _env_int("MAX_CODEBASE_CHARS", 800000)  # ~200k tokens - safe for 1M limit
    )
    # Higher budget reserved for whole-repo ingestion (github_ingest_repository),
    # which traverses the FULL tree deterministically rather than letting the LLM
    # hand-pick files. raw_codebase is stored verbatim; the per-turn LLM budget is
    # still enforced downstream by TokenSafetyPlugin / synthesis_budget_callback,
    # so a larger ingest budget does NOT increase what is sent to Gemini per turn.
    max_repo_codebase_chars: int = Field(default_factory=lambda: _env_int("MAX_REPO_CODEBASE_CHARS", 4000000))

    # Rate Limiting & Resilience
    max_concurrency: int = Field(default_factory=lambda: _env_int("MAX_CONCURRENCY", 2))
    max_retries: int = Field(default_factory=lambda: _env_int("MAX_RETRIES", 5))

    def generation_config(self, temperature: float | None = None):
        """safety_config plus an optional task-tuned sampling temperature."""
        cfg = self.safety_config
        if temperature is not None:
            cfg.temperature = temperature
        return cfg

    # Global safety settings — typed correctly so ADK actually applies them.
    @property
    def safety_config(self):
        from google.genai import types as genai_types

        return genai_types.GenerateContentConfig(
            # Global ceiling so no generation can run unbounded. A small model
            # (e.g. the flash-lite root/supervisor) that degenerates into a
            # token-repetition loop would otherwise stream until its context
            # limit, surfacing as a "frozen / infinite" UI. Agents needing more
            # (html_agent) override this on their own generate_content_config.
            max_output_tokens=_env_int("MAX_OUTPUT_TOKENS", 8192),
            http_options=genai_types.HttpOptions(
                # 429 quota errors need real waiting: exponential backoff up to
                # 60s with jitter, retrying the standard transient status codes.
                # The old initial_delay=1.0 with no max_delay burned all
                # attempts in seconds — far quicker than RPM quota recovers.
                retry_options=genai_types.HttpRetryOptions(
                    attempts=self.max_retries,
                    initial_delay=2.0,
                    max_delay=60.0,
                    exp_base=2.0,
                    jitter=0.5,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                )
            ),
            safety_settings=[
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                # Danger category often has false positives for code snippets (e.g. security audits)
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_ONLY_HIGH",
                ),
            ],
        )
