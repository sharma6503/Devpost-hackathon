from __future__ import annotations
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from google.adk.skills.models import Skill
from google.adk.tools.skill_toolset import SkillToolset
from agent_guardian.utils.skill_loader import (
    get_configured_skill_names,
    get_gcp_skill_registry,
    fetch_configured_gcp_skills,
    compile_skills_to_markdown,
    get_merged_ruleset,
    get_skill_toolset,
    invalidate_skill_toolsets,
)


def test_get_configured_skill_names():
    """Verify parsing of GCP_SKILLS and SKILLS environment variables."""
    # Scenario A: Empty / unset
    with patch.dict(os.environ, {}, clear=True):
        assert get_configured_skill_names() == []

    # Scenario B: GCP_SKILLS with whitespace and multiple entries
    with patch.dict(os.environ, {"GCP_SKILLS": "governance-audit,  implementation-standards , pilot-to-prod "}, clear=True):
        names = get_configured_skill_names()
        assert names == ["governance-audit", "implementation-standards", "pilot-to-prod"]

    # Scenario C: SKILLS fallback
    with patch.dict(os.environ, {"SKILLS": "a2a-compliance-rules, grc-documents"}, clear=True):
        names = get_configured_skill_names()
        assert names == ["a2a-compliance-rules", "grc-documents"]


def test_get_gcp_skill_registry():
    """Verify GCPSkillRegistry instantiation with environment variables and fallback."""
    # Scenario A: No project set
    with patch.dict(os.environ, {}, clear=True):
        reg = get_gcp_skill_registry()
        assert reg is None

    # Scenario B: Project and location set
    with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "global"}):
        reg = get_gcp_skill_registry()
        assert reg is not None
        assert reg.project_id == "test-project"
        assert reg.location == "global"


@pytest.mark.asyncio
async def test_fetch_configured_gcp_skills_success():
    """Verify async fetching of configured skills from GCP Skill Registry."""
    invalidate_skill_toolsets()

    mock_skill_1 = MagicMock(spec=Skill)
    mock_skill_1.name = "governance-audit"
    mock_skill_1.description = "Governance audit rules"

    mock_skill_2 = MagicMock(spec=Skill)
    mock_skill_2.name = "implementation-standards"
    mock_skill_2.description = "Implementation standards"

    mock_registry = MagicMock()
    mock_registry.get_skill = AsyncMock(side_effect=lambda name: mock_skill_1 if name == "governance-audit" else mock_skill_2)

    with patch.dict(os.environ, {"GCP_SKILLS": "governance-audit, implementation-standards"}):
        skills = await fetch_configured_gcp_skills(registry=mock_registry, use_cache=True)
        assert len(skills) == 2
        assert skills[0].name == "governance-audit"
        assert skills[1].name == "implementation-standards"
        assert mock_registry.get_skill.call_count == 2


@pytest.mark.asyncio
async def test_fetch_configured_gcp_skills_missing_or_error():
    """Verify graceful handling when skills fail to fetch or registry is absent."""
    invalidate_skill_toolsets()

    # Scenario A: Registry is None
    skills = await fetch_configured_gcp_skills(skill_names=["test-skill"], registry=None)
    assert skills == []

    # Scenario B: Registry raises an exception on fetch
    mock_registry = MagicMock()
    mock_registry.get_skill = AsyncMock(side_effect=RuntimeError("API Network Error"))
    skills = await fetch_configured_gcp_skills(skill_names=["failing-skill"], registry=mock_registry, use_cache=False)
    assert skills == []


def test_compile_skills_to_markdown():
    """Verify compilation of GCP Skill objects into structured markdown rules."""
    mock_frontmatter_1 = MagicMock()
    mock_frontmatter_1.name = "skill-one"
    mock_frontmatter_1.description = "First test skill"

    skill_1 = MagicMock(spec=Skill)
    skill_1.name = "skill-one"
    skill_1.description = "First test skill"
    skill_1.frontmatter = mock_frontmatter_1
    skill_1.instructions = "Rule #1: Be fast."
    mock_res_1 = MagicMock()
    mock_res_1.references = {"rules.md": "The fast rules manifest."}
    skill_1.resources = mock_res_1

    skill_2 = MagicMock(spec=Skill)
    skill_2.name = "skill-two"
    skill_2.description = "Second test skill"
    skill_2.instructions = "Rule #2: Be precise."
    mock_res_2 = MagicMock()
    mock_res_2.references = {}
    skill_2.resources = mock_res_2

    markdown = compile_skills_to_markdown([skill_1, skill_2])

    assert "=== 🛠️ GCP SKILLS REGISTRY STANDARDS & PLAYBOOKS ===" in markdown
    assert "### Skill: skill-one" in markdown
    assert "**Description**: First test skill" in markdown
    assert "Rule #1: Be fast." in markdown
    assert "#### Reference File: `references/rules.md`" in markdown
    assert "The fast rules manifest." in markdown

    assert "### Skill: skill-two" in markdown
    assert "**Description**: Second test skill" in markdown
    assert "Rule #2: Be precise." in markdown


def test_compile_skills_empty():
    """Verify compiling an empty skill list returns an empty string."""
    assert compile_skills_to_markdown([]) == ""


@pytest.mark.asyncio
async def test_get_merged_ruleset_no_skills():
    """Verify that get_merged_ruleset returns the base confluence rules if no skills are loaded."""
    with patch(
        "agent_guardian.utils.skill_loader.fetch_configured_gcp_skills",
        new_callable=AsyncMock,
        return_value=[],
    ):
        merged = await get_merged_ruleset("base_confluence_rules")
        assert merged == "base_confluence_rules"


@pytest.mark.asyncio
async def test_get_merged_ruleset_success():
    """Verify merging of Confluence base rules with fetched GCP skills."""
    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "gcp-audit-skill"
    mock_skill.description = "A standard GCP skill"
    mock_skill.instructions = "GCP Audit instructions"
    mock_res_3 = MagicMock()
    mock_res_3.references = {}
    mock_skill.resources = mock_res_3

    # Scenario A: Confluence rules are available
    merged_a = await get_merged_ruleset("Base Corporate Rules", skills=[mock_skill])
    assert "Base Corporate Rules" in merged_a
    assert "=== 🛠️ GCP SKILLS REGISTRY STANDARDS & PLAYBOOKS ===" in merged_a
    assert "### Skill: gcp-audit-skill" in merged_a

    # Scenario B: Confluence is unavailable or empty
    merged_b = await get_merged_ruleset("[CONFLUENCE_UNAVAILABLE] Not found", skills=[mock_skill])
    assert "[CONFLUENCE_UNAVAILABLE]" not in merged_b
    assert "=== 🛠️ GCP SKILLS REGISTRY STANDARDS & PLAYBOOKS ===" in merged_b
    assert "### Skill: gcp-audit-skill" in merged_b


def test_get_skill_toolset():
    """Verify SkillToolset construction and caching with GCP Skill Registry."""
    invalidate_skill_toolsets()

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "unit-test-skill"
    mock_skill.description = "A skill for unit testing"
    mock_skill.instructions = "Instructions"
    mock_skill.resources = MagicMock()
    mock_skill.resources.references = {}

    with patch("agent_guardian.utils.skill_loader.get_gcp_skill_registry", return_value=None):
        toolset = get_skill_toolset(skills=[mock_skill], use_registry=False, use_cache=False)
        assert isinstance(toolset, SkillToolset)
        tool_names = [t.name for t in toolset._tools]
        assert "list_skills" in tool_names
        assert "load_skill" in tool_names
        assert "load_skill_resource" in tool_names
        assert "run_skill_script" in tool_names
        assert "search_skills" not in tool_names

    # With mock registry -> search_skills is included
    mock_reg = MagicMock()
    mock_reg.search_tool_description.return_value = "Search GCP remote skills"

    with patch("agent_guardian.utils.skill_loader.get_gcp_skill_registry", return_value=mock_reg):
        toolset_reg = get_skill_toolset(skills=[mock_skill], use_registry=True, use_cache=False)
        assert isinstance(toolset_reg, SkillToolset)
        tool_names_reg = [t.name for t in toolset_reg._tools]
        assert "search_skills" in tool_names_reg


def test_load_local_skills_discovery(tmp_path):
    """Verify local skill discovery from directories."""
    from agent_guardian.utils.skill_loader import load_local_skills
    invalidate_skill_toolsets()

    skill_dir = tmp_path / "mock-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: mock-skill\ndescription: A mock local skill\n---\n# Instructions\nRule 1",
        encoding="utf-8",
    )

    with patch.dict(os.environ, {"SKILLS_DIR": str(tmp_path)}):
        skills = load_local_skills()
        assert any(s.name == "mock-skill" for s in skills)


@pytest.mark.asyncio
async def test_fetch_configured_gcp_skills_with_local_fallback(tmp_path):
    """Verify fallback to local skill when GCP Skill Registry returns error or is unavailable."""
    invalidate_skill_toolsets()

    skill_dir = tmp_path / "offline-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: offline-skill\ndescription: Offline fallback skill\n---\n# Instructions\nDo things offline",
        encoding="utf-8",
    )

    mock_registry = MagicMock()
    mock_registry.get_skill = AsyncMock(side_effect=RuntimeError("GCP 404 Not Found"))

    with patch.dict(os.environ, {"SKILLS_DIR": str(tmp_path)}):
        skills = await fetch_configured_gcp_skills(
            skill_names=["offline-skill"],
            registry=mock_registry,
            use_cache=False,
        )
        assert len(skills) == 1
        assert skills[0].name == "offline-skill"

