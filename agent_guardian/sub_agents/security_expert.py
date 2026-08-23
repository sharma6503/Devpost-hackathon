from __future__ import annotations

"""
Security & Deployment Expert Agent.

Role in Pipeline:
Executes within the `parallel_review_experts` group during the Quality Gate Loop.
Specializes in detecting hardcoded secrets, injection risks, dependency freshness, and deployment misconfigurations.

State Interactions:
- Reads: `code_logic`, `code_config`, `confluence_rules`, `is_large_codebase`, `review_plan`, `module_map`
- Writes: `security_review_result`
"""

from ..config import Config
from ..prompts import SECURITY_EXPERT_PROMPT
from ._expert_factory import make_expert_agent

_cfg = Config()

security_expert = make_expert_agent(
    name="security_expert",
    model=_cfg.agent_settings.security_model,
    description="Security and cloud deployment expert — secrets, deps, IAM, Cloud Run.",
    instruction=SECURITY_EXPERT_PROMPT,
    output_key="security_review_result",
)
