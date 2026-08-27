from __future__ import annotations
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from google.adk.skills.models import Skill, Frontmatter
from google.adk.tools.skill_toolset import SkillToolset
from agent_guardian.utils.skill_loader import (
    normalize_skill_name,
    get_configured_skill_names,
    get_gcp_skill_registry,
    fetch_skill_by_name,
    search_gcp_skills,
    search_and_fetch_gcp_skills,
    fetch_configured_gcp_skills,
    compile_skills_to_markdown,
    get_merged_ruleset,
    get_skill_toolset,
    invalidate_skill_toolsets,
)


def test_normalize_skill_name():
    """Verify skill name normalization and sanitization across various formats."""
    assert normalize_skill_name("") == ""
    assert normalize_skill_name("  governance-audit  ") == "governance-audit"
    assert normalize_skill_name("'security-scan'") == "security-scan"
    assert normalize_skill_name('"cloud-run"') == "cloud-run"
    assert normalize_skill_name("projects/test-proj/locations/us-central1/skills/cloud-sql") == "cloud-sql"
    assert normalize_skill_name("skills/my-custom-skill/SKILL.md") == "my-custom-skill"
    assert normalize_skill_name("skills/my-custom-skill/skill.md") == "my-custom-skill"
    assert normalize_skill_name("My Custom Skill") == "my-custom-skill"
    assert normalize_skill_name("test_skill_name") == "test-skill-name"


def test_get_configured_skill_names():
    """Verify parsing of GCP_SKILLS and SKILLS environment variables."""
    # Scenario A: Empty / unset
    with patch.dict(os.environ, {}, clear=True):
        assert get_configured_skill_names() == []

    # Scenario B: GCP_SKILLS with whitespace and multiple entries
    with patch.dict(os.environ, {"GCP_SKILLS": "governance-audit,  implementation-standards , 'pilot-to-prod' "}, clear=True):
        names = get_configured_skill_names()
        assert names == ["governance-audit", "implementation-standards", "pilot-to-prod"]

    # Scenario C: SKILLS fallback with full GCP paths
    with patch.dict(os.environ, {"SKILLS": "projects/123/locations/us-central1/skills/a2a-compliance-rules, grc-documents"}, clear=True):
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
async def test_fetch_skill_by_name():
    """Verify fetch_skill_by_name with remote registry and caching."""
    invalidate_skill_toolsets()

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "governance-audit"
    mock_skill.description = "Governance audit rules"

    mock_registry = MagicMock()
    mock_registry.get_skill = AsyncMock(return_value=mock_skill)

    # Remote fetch success
    skill = await fetch_skill_by_name("projects/p/locations/l/skills/governance-audit", registry=mock_registry, use_cache=True)
    assert skill is not None
    assert skill.name == "governance-audit"
    mock_registry.get_skill.assert_called_once_with(name="governance-audit")

    # Cache hit
    skill_cached = await fetch_skill_by_name("governance-audit", registry=mock_registry, use_cache=True)
    assert skill_cached is mock_skill
    assert mock_registry.get_skill.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_search_gcp_skills():
    """Verify search_gcp_skills queries the registry."""
    invalidate_skill_toolsets()

    mock_fm1 = MagicMock(spec=Frontmatter)
    mock_fm1.name = "gcp-cloud-run"
    mock_fm2 = MagicMock(spec=Frontmatter)
    mock_fm2.name = "gcp-cloud-sql"

    mock_registry = MagicMock()
    mock_registry.search_skills = AsyncMock(return_value=[mock_fm1, mock_fm2])

    results = await search_gcp_skills("cloud", registry=mock_registry)
    assert len(results) == 2
    assert results[0].name == "gcp-cloud-run"
    mock_registry.search_skills.assert_called_once_with(query="cloud")

    # Empty query returns empty list immediately
    empty_results = await search_gcp_skills("", registry=mock_registry)
    assert empty_results == []


@pytest.mark.asyncio
async def test_search_and_fetch_gcp_skills():
    """Verify search_and_fetch_gcp_skills retrieves full Skill objects for search results."""
    invalidate_skill_toolsets()

    mock_fm = MagicMock(spec=Frontmatter)
    mock_fm.name = "gcp-storage"

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "gcp-storage"
    mock_skill.description = "Google Cloud Storage Skill"

    mock_registry = MagicMock()
    mock_registry.search_skills = AsyncMock(return_value=[mock_fm])
    mock_registry.get_skill = AsyncMock(return_value=mock_skill)

    skills = await search_and_fetch_gcp_skills("storage", registry=mock_registry, limit=5)
    assert len(skills) == 1
    assert skills[0].name == "gcp-storage"


@pytest.mark.asyncio
async def test_fetch_configured_gcp_skills_with_search_queries():
    """Verify dynamic discovery via search_queries in fetch_configured_gcp_skills."""
    invalidate_skill_toolsets()

    mock_fm = MagicMock(spec=Frontmatter)
    mock_fm.name = "discovered-skill"

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "discovered-skill"
    mock_skill.description = "Discovered Skill"

    mock_registry = MagicMock()
    mock_registry.search_skills = AsyncMock(return_value=[mock_fm])
    mock_registry.get_skill = AsyncMock(return_value=mock_skill)

    with patch.dict(os.environ, {}, clear=True):
        skills = await fetch_configured_gcp_skills(
            skill_names=None,
            registry=mock_registry,
            search_queries=["governance"],
        )
        assert any(s.name == "discovered-skill" for s in skills)


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


def test_compile_skills_to_markdown_with_bytes_and_assets():
    """Verify compilation of GCP Skill objects into structured markdown rules with byte references and assets."""
    mock_frontmatter_1 = MagicMock()
    mock_frontmatter_1.name = "skill-one"
    mock_frontmatter_1.description = "First test skill"

    skill_1 = MagicMock(spec=Skill)
    skill_1.name = "skill-one"
    skill_1.description = "First test skill"
    skill_1.frontmatter = mock_frontmatter_1
    skill_1.instructions = "Rule #1: Be fast."
    mock_res_1 = MagicMock()
    mock_res_1.references = {"rules.md": b"The fast rules manifest from bytes."}
    mock_res_1.assets = {"schema.json": b"{}"}
    skill_1.resources = mock_res_1

    skill_2 = MagicMock(spec=Skill)
    skill_2.name = "skill-two"
    skill_2.description = "Second test skill"
    skill_2.instructions = "Rule #2: Be precise."
    mock_res_2 = MagicMock()
    mock_res_2.references = {}
    mock_res_2.assets = {}
    skill_2.resources = mock_res_2

    markdown = compile_skills_to_markdown([skill_1, skill_2])

    assert "=== 🛠️ GCP SKILLS REGISTRY STANDARDS & PLAYBOOKS ===" in markdown
    assert "### Skill: skill-one" in markdown
    assert "**Description**: First test skill" in markdown
    assert "Rule #1: Be fast." in markdown
    assert "#### Reference File: `references/rules.md`" in markdown
    assert "The fast rules manifest from bytes." in markdown
    assert "**Available Assets**:" in markdown
    assert "- `assets/schema.json`" in markdown

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
    mock_res_3.assets = {}
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
    mock_skill.resources.assets = {}

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


@pytest.mark.asyncio
async def test_merge_local_skills_workflow_callback():
    """Verify _merge_local_skills_callback in review.py properly stores retrieved_gcp_skills."""
    from agent_guardian.workflows.review import _merge_local_skills_callback

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "workflow-skill"
    mock_skill.description = "Workflow skill description"
    mock_skill.instructions = "Instructions for workflow"
    mock_res = MagicMock()
    mock_res.references = {}
    mock_res.assets = {}
    mock_skill.resources = mock_res

    mock_ctx = MagicMock()
    mock_ctx.state = {
        "confluence_rules": "Corporate Policy",
        "gcp_skills": "workflow-skill",
    }

    with patch("agent_guardian.utils.skill_loader.fetch_configured_gcp_skills", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [mock_skill]
        await _merge_local_skills_callback(mock_ctx)

        assert "Corporate Policy" in mock_ctx.state["confluence_rules"]
        assert "### Skill: workflow-skill" in mock_ctx.state["confluence_rules"]
        assert mock_ctx.state["retrieved_gcp_skills"] == [
            {"name": "workflow-skill", "description": "Workflow skill description"}
        ]


@pytest.mark.asyncio
async def test_pull_gcp_skill_tool_success():
    """Verify pull_gcp_skill tool retrieves skill instructions and formats output."""
    from agent_guardian.tools.gcp_skill_tool import pull_gcp_skill

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "agent-platform-prompt-management"
    mock_skill.description = "Enterprise prompt governance standard"
    mock_skill.instructions = "# Prompt Rules\nAlways version prompts."
    mock_res = MagicMock()
    mock_res.list_references.return_value = ["references/create.md"]
    mock_res.list_assets.return_value = []
    mock_res.get_reference.return_value = "# Reference Documentation"
    mock_skill.resources = mock_res

    with patch("agent_guardian.tools.gcp_skill_tool.fetch_skill_by_name", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_skill

        result = await pull_gcp_skill("agent-platform-prompt-management", include_resources=True)
        assert result["status"] == "success"
        assert result["skill_name"] == "agent-platform-prompt-management"
        assert "Always version prompts" in result["instructions"]
        assert "references/create.md" in result["resources"]
        assert result["resources"]["references/create.md"] == "# Reference Documentation"
        assert "Successfully pulled GCP skill" in result["message"]


@pytest.mark.asyncio
async def test_pull_gcp_skill_tool_not_found():
    """Verify pull_gcp_skill tool returns error when skill is missing."""
    from agent_guardian.tools.gcp_skill_tool import pull_gcp_skill

    with patch("agent_guardian.tools.gcp_skill_tool.fetch_skill_by_name", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        result = await pull_gcp_skill("non-existent-skill")
        assert result["status"] == "error"
        assert "was not found" in result["message"]

    # Empty name check
    empty_result = await pull_gcp_skill("")
    assert empty_result["status"] == "error"
    assert "No skill name provided" in empty_result["message"]


@pytest.mark.asyncio
async def test_pull_gcp_skill_tool_state_update():
    """Verify pull_gcp_skill tool updates session state and merges confluence_rules."""
    from agent_guardian.tools.gcp_skill_tool import pull_gcp_skill

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "gke-cost-optimization"
    mock_skill.description = "GKE cost optimization rules"
    mock_skill.instructions = "Use spot instances."
    mock_skill.resources = None

    mock_context = MagicMock()
    mock_context.state = {
        "confluence_rules": "Existing Policy",
        "pulled_gcp_skills": [],
    }

    with patch("agent_guardian.tools.gcp_skill_tool.fetch_skill_by_name", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_skill

        result = await pull_gcp_skill("gke-cost-optimization", tool_context=mock_context)
        assert result["status"] == "success"
        assert "gke-cost-optimization" in mock_context.state["pulled_gcp_skills"]
        assert "Existing Policy" in mock_context.state["confluence_rules"]
        assert "gke-cost-optimization" in mock_context.state["confluence_rules"]


@pytest.mark.asyncio
async def test_list_available_gcp_skills_tool():
    """Verify list_available_gcp_skills tool queries the registry."""
    from agent_guardian.tools.gcp_skill_tool import list_available_gcp_skills

    mock_fm = MagicMock(spec=Frontmatter)
    mock_fm.name = "agent-platform-inference"
    mock_fm.description = "Inference optimization guidelines"

    mock_reg = MagicMock()
    mock_reg.search_skills = AsyncMock(return_value=[mock_fm])

    with patch("agent_guardian.tools.gcp_skill_tool.get_gcp_skill_registry", return_value=mock_reg):
        res = await list_available_gcp_skills(query="inference")
        assert res["status"] == "success"
        assert res["total_skills"] == 1
        assert res["skills"][0]["name"] == "agent-platform-inference"


@pytest.mark.asyncio
async def test_pull_multiple_gcp_skills_tool():
    """Verify pull_multiple_gcp_skills tool handles list and comma-separated inputs."""
    from agent_guardian.tools.gcp_skill_tool import pull_multiple_gcp_skills

    mock_skill1 = MagicMock(spec=Skill)
    mock_skill1.name = "skill-one"
    mock_skill1.description = "First skill"
    mock_skill1.instructions = "Rule 1"
    mock_skill1.resources = None

    mock_skill2 = MagicMock(spec=Skill)
    mock_skill2.name = "skill-two"
    mock_skill2.description = "Second skill"
    mock_skill2.instructions = "Rule 2"
    mock_skill2.resources = None

    async def _mock_fetch(name, **kwargs):
        if name == "skill-one":
            return mock_skill1
        if name == "skill-two":
            return mock_skill2
        return None

    with patch("agent_guardian.tools.gcp_skill_tool.fetch_skill_by_name", side_effect=_mock_fetch):
        # Comma-separated string
        res = await pull_multiple_gcp_skills("skill-one, skill-two")
        assert res["status"] == "success"
        assert res["loaded_count"] == 2
        assert len(res["skills"]) == 2
        assert "### Skill: skill-one" in res["compiled_rules"]
        assert "### Skill: skill-two" in res["compiled_rules"]


def test_gcp_skill_tools_in_agent_and_experts():
    """Verify pull_gcp_skill and list_available_gcp_skills are registered in root_agent, expert factory, and followup."""
    from agent_guardian.tools.gcp_skill_tool import pull_gcp_skill, list_available_gcp_skills
    from agent_guardian.sub_agents._expert_factory import get_base_tools
    from agent_guardian.sub_agents.followup_agent import _tools as followup_tools

    base_tools = get_base_tools()
    assert pull_gcp_skill in base_tools
    assert list_available_gcp_skills in base_tools

    assert pull_gcp_skill in followup_tools
    assert list_available_gcp_skills in followup_tools



