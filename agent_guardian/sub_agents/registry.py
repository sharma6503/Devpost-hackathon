from __future__ import annotations

"""
registry.py — Single source of truth for the review-expert fleet.

Before this existed, adding (or renaming) an expert required synchronized edits
in four places with silent failure modes:
  * evaluation_expert's agent-name → state-key map (revision routing broke),
  * html_agent's _EXPERT_SECTIONS and expert_keys lists (report dropped the
    expert silently),
  * agent.py's resilient-wrapping list,
  * the workflow fan-out edges.

This module holds the metadata; consumers derive their structures from
EXPERT_REGISTRY. It is deliberately pure data — importing agent objects here
would create import cycles with the sub_agent modules.
"""

from dataclasses import dataclass, field


def normalize_expert_name(name: str) -> str:
    """Normalize expert agent names to standard snake_case IDs."""
    cleaned = str(name).lower().strip().replace(" ", "_").replace("-", "_")
    if cleaned in ("adk", "adk_expert", "architecture_expert", "architecture_and_framework_expert"):
        return "adk_expert"
    if cleaned in ("quality", "quality_expert", "code_quality_expert", "code_quality"):
        return "quality_expert"
    if cleaned in ("security", "security_expert", "security_deployment_expert", "deployment_expert"):
        return "security_expert"
    if cleaned in ("governance", "governance_expert", "governance_compliance_expert", "compliance_expert"):
        return "governance_expert"
    return cleaned


@dataclass(frozen=True)
class ExpertSpec:
    """Metadata for one review expert."""

    agent_name: str  # LlmAgent.name
    state_key: str  # LlmAgent.output_key
    display_title: str  # Section heading in the HTML report
    icon: str  # Material Symbols icon name
    accent: str  # Tailwind accent class for the report
    aliases: tuple[str, ...] = field(default_factory=tuple)  # legacy/judge names


# Order matters: this is the section order in the HTML report.
EXPERT_REGISTRY: tuple[ExpertSpec, ...] = (
    ExpertSpec(
        agent_name="governance_expert",
        state_key="governance_review_result",
        display_title="Governance & Compliance",
        icon="gavel",
        accent="text-error",
    ),
    ExpertSpec(
        agent_name="security_expert",
        state_key="security_review_result",
        display_title="Security & Deployment",
        icon="security",
        accent="text-error",
    ),
    ExpertSpec(
        agent_name="code_quality_expert",
        state_key="quality_review_result",
        display_title="Code Quality",
        icon="code_blocks",
        accent="text-primary",
        aliases=("quality_expert",),
    ),
    ExpertSpec(
        agent_name="architecture_and_framework_expert",
        state_key="adk_review_result",
        display_title="ADK Architecture",
        icon="hub",
        accent="text-secondary",
        aliases=("adk_expert",),
    ),
    ExpertSpec(
        agent_name="code_validator_agent",
        state_key="validation_result",
        display_title="Code Validation",
        icon="verified",
        accent="text-tertiary",
    ),
)

# All expert output state keys, in report order.
EXPERT_STATE_KEYS: tuple[str, ...] = tuple(s.state_key for s in EXPERT_REGISTRY)

# Any accepted name (canonical or alias) → state key. Used by the evaluation
# quality gate to locate the weakest expert's review for revision.
AGENT_NAME_TO_STATE_KEY: dict[str, str] = {
    name: spec.state_key for spec in EXPERT_REGISTRY for name in (spec.agent_name, *spec.aliases)
}
