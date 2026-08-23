from __future__ import annotations

"""
Synthesis Agent — Global Narrative Aggregator.

Role in Pipeline:
Runs after the Quality Gate Loop successfully completes.
Synthesizes the individual expert reports (`adk_review_result`, `quality_review_result`, etc.)
into a single, cohesive Markdown document. It creates the "Global Narrative" while preserving
the technical depth and specific findings from the experts.

State Interactions:
- Reads: `adk_review_result`, `quality_review_result`, `security_review_result`, `governance_review_result`, `validation_result`
- Writes: `synthesis_result`
"""

from google.adk.agents import LlmAgent
from agent_guardian.config import Config
from agent_guardian.prompts import SYNTHESIS_PROMPT
from ..utils.token_utils import synthesis_budget_callback

_cfg = Config()

# Build a synthesis-specific config: inherit the safety settings but also
# cap output tokens so large reports don't time out or hit quota.
# Higher temperature: synthesis writes prose, not structured output.
_synthesis_config = _cfg.generation_config(temperature=_cfg.agent_settings.synthesis_temperature)
_synthesis_config.max_output_tokens = 32768

synthesis_agent = LlmAgent(
    name="synthesis_agent",
    model=_cfg.agent_settings.synthesis_model,
    description="Combines expert reviews into a polished Markdown report.",
    instruction=SYNTHESIS_PROMPT,
    output_key="synthesis_result",
    include_contents="none",  # LATENCY: all expert results come via state injection
    before_agent_callback=synthesis_budget_callback,
    generate_content_config=_synthesis_config,
)
