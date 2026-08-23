"""Registry consistency: the expert registry must match the live agent objects.

If an expert is renamed or its output_key changes without updating
sub_agents/registry.py, revision routing and the HTML report silently break.
These tests turn that silent break into a loud one.
"""

from agent_guardian.sub_agents.registry import (
    AGENT_NAME_TO_STATE_KEY,
    EXPERT_REGISTRY,
    EXPERT_STATE_KEYS,
)


def _live_experts():
    from agent_guardian.sub_agents.adk_expert import adk_expert
    from agent_guardian.sub_agents.code_validator_agent import code_validator_agent
    from agent_guardian.sub_agents.governance_expert import governance_expert
    from agent_guardian.sub_agents.quality_expert import quality_expert
    from agent_guardian.sub_agents.security_expert import security_expert

    return [
        adk_expert,
        quality_expert,
        security_expert,
        governance_expert,
        code_validator_agent,
    ]


def test_registry_matches_live_agent_names_and_output_keys():
    by_name = {spec.agent_name: spec for spec in EXPERT_REGISTRY}
    for agent in _live_experts():
        assert agent.name in by_name, f"Agent {agent.name!r} is missing from EXPERT_REGISTRY (sub_agents/registry.py)"
        assert by_name[agent.name].state_key == agent.output_key, (
            f"Registry state_key for {agent.name!r} is "
            f"{by_name[agent.name].state_key!r} but the agent writes "
            f"{agent.output_key!r}"
        )


def test_registry_covers_every_live_expert_exactly_once():
    live_names = {a.name for a in _live_experts()}
    registry_names = {spec.agent_name for spec in EXPERT_REGISTRY}
    assert live_names == registry_names


def test_state_keys_are_unique_and_ordered():
    assert len(set(EXPERT_STATE_KEYS)) == len(EXPERT_STATE_KEYS)
    assert EXPERT_STATE_KEYS == tuple(s.state_key for s in EXPERT_REGISTRY)


def test_alias_map_resolves_canonical_and_alias_names():
    assert AGENT_NAME_TO_STATE_KEY["adk_expert"] == "adk_review_result"
    assert AGENT_NAME_TO_STATE_KEY["architecture_and_framework_expert"] == "adk_review_result"
    assert AGENT_NAME_TO_STATE_KEY["quality_expert"] == "quality_review_result"
    assert AGENT_NAME_TO_STATE_KEY["code_quality_expert"] == "quality_review_result"
    assert AGENT_NAME_TO_STATE_KEY["code_validator_agent"] == "validation_result"
