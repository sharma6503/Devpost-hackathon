from __future__ import annotations

"""
Code Quality Expert Agent.

Role in Pipeline:
Executes within the `parallel_review_experts` group during the Quality Gate Loop.
Specializes in evaluating Python code readability, maintainability, typing, and standard practices.
Generates an audit report tailored to the rules fetched by the `confluence_rules_agent`.

State Interactions:
- Reads: `code_logic`, `code_config`, `confluence_rules`, `is_large_codebase`, `review_plan`, `module_map`
- Writes: `quality_review_result`
"""

from ..config import Config
from ..prompts import QUALITY_EXPERT_PROMPT
from ._expert_factory import make_expert_agent

_cfg = Config()

quality_expert = make_expert_agent(
    name="code_quality_expert",
    model=_cfg.agent_settings.quality_model,
    description="Expert Python code quality reviewer — types, docs, errors, tests.",
    instruction=QUALITY_EXPERT_PROMPT,
    output_key="quality_review_result",
)
