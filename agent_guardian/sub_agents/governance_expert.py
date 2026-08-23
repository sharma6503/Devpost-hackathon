from __future__ import annotations

"""
Governance & Compliance Expert Agent.

Role in Pipeline:
Executes within the `parallel_review_experts` group during the Quality Gate Loop.
Acts as the Chief Compliance Officer, enforcing Tier 1 (Hard Gate) and Tier 2 (Soft Gate) rules.
Uses `scan_governance` to perform AST-based and regex-based technical scanning before forming a verdict.

State Interactions:
- Reads: `code_logic`, `code_config`, `code_docs`, `confluence_rules`, `is_large_codebase`, `review_plan`, `module_map`
- Writes: `governance_review_result`
"""

from agent_guardian.tools.governance_tools import scan_governance
from ..config import Config
from ..prompts import GOVERNANCE_EXPERT_PROMPT
from ._expert_factory import make_expert_agent

_cfg = Config()

governance_expert = make_expert_agent(
    name="governance_expert",
    model=_cfg.agent_settings.governance_model,
    description=(
        "Chief Compliance Officer — audits AI agents against all 28 governance rules. "
        "Validates against live Confluence standards fetched into session state. "
        "Hard Gate failures produce immediate REJECTED verdict."
    ),
    instruction=GOVERNANCE_EXPERT_PROMPT,
    output_key="governance_review_result",
    extra_tools=[scan_governance],
)
