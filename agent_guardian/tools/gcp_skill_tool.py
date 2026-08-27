from __future__ import annotations

"""
gcp_skill_tool.py — Dedicated tool for pulling and querying Google Cloud Platform (GCP) skills.

Allows agents (Supervisor, Review Experts, Follow-up, Remediation) to dynamically
pull, inspect, and enforce GCP enterprise skill standards (e.g. Prompt Management,
Inference Optimization, Cloud Armor WAF, GKE Best Practices) from the Google Cloud
Skill Registry (`agentregistry.googleapis.com`) or local fallback registries.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from google.adk.tools.tool_context import ToolContext

from ..utils.skill_loader import (
    compile_skills_to_markdown,
    fetch_skill_by_name,
    get_gcp_skill_registry,
    normalize_skill_name,
)

logger = logging.getLogger(__name__)


async def pull_gcp_skill(
    skill_name: str,
    include_resources: bool = True,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Dedicated tool to pull and retrieve a Google Cloud Platform (GCP) Skill from the GCP Agent Registry.

    Downloads and extracts enterprise governance, security, architecture, and optimization standards
    (e.g., 'agent-platform-prompt-management', 'agent-platform-inference', 'gke-cost-optimization',
    'google-cloud-waf-security', etc.) directly from the Google Cloud Skill Registry.

    Args:
        skill_name: The name or resource identifier of the skill (e.g., 'agent-platform-prompt-management').
        include_resources: Whether to include text contents of bundled reference files (e.g., 'references/create.md').
        tool_context: Optional ADK ToolContext injected during runtime execution.

    Returns:
        A dict with:
          - "status": "success" or "error"
          - "skill_name": Canonical skill name
          - "description": Description of the skill
          - "instructions": Full text markdown instructions and guidelines from the skill
          - "resources": Dict mapping resource paths to their text contents (if include_resources=True)
          - "resource_files": List of available resource filenames
          - "message": Human-readable summary message
    """
    if not skill_name or not skill_name.strip():
        return {
            "status": "error",
            "skill_name": "",
            "description": "",
            "instructions": "",
            "resources": {},
            "resource_files": [],
            "message": "No skill name provided. Please specify a valid GCP skill name (e.g., 'agent-platform-prompt-management').",
        }

    raw_name = skill_name.strip()
    logger.info("pull_gcp_skill: pulling GCP skill '%s'", raw_name)

    try:
        skill = await fetch_skill_by_name(raw_name)
    except Exception as e:
        logger.error("pull_gcp_skill: error retrieving '%s': %s", raw_name, e)
        return {
            "status": "error",
            "skill_name": raw_name,
            "description": "",
            "instructions": "",
            "resources": {},
            "resource_files": [],
            "message": f"Failed to pull GCP skill '{raw_name}': {e}",
        }

    if skill is None:
        return {
            "status": "error",
            "skill_name": raw_name,
            "description": "",
            "instructions": "",
            "resources": {},
            "resource_files": [],
            "message": f"GCP skill '{raw_name}' was not found in the Google Cloud Skill Registry or local caches.",
        }

    # Extract resource contents and file lists
    resources_dict: Dict[str, str] = {}
    resource_files: List[str] = []

    if hasattr(skill, "resources") and skill.resources is not None:
        if hasattr(skill.resources, "list_references"):
            resource_files.extend(skill.resources.list_references())
        if hasattr(skill.resources, "list_assets"):
            resource_files.extend(skill.resources.list_assets())

        if include_resources:
            for ref_name in resource_files:
                try:
                    content = skill.resources.get_reference(ref_name)
                    if content is None and hasattr(skill.resources, "get_asset"):
                        content = skill.resources.get_asset(ref_name)
                    if content is not None:
                        if isinstance(content, bytes):
                            resources_dict[ref_name] = content.decode("utf-8", errors="replace")
                        else:
                            resources_dict[ref_name] = str(content)
                except Exception as res_err:
                    logger.debug("pull_gcp_skill: error reading resource '%s': %s", ref_name, res_err)

    # If runtime context is present, save the skill to session state for downstream review nodes
    if tool_context is not None and hasattr(tool_context, "state") and isinstance(tool_context.state, dict):
        pulled = tool_context.state.setdefault("pulled_gcp_skills", [])
        if skill.name not in pulled:
            pulled.append(skill.name)

        # Merge compiled skill instructions into active rules if not already present
        existing_rules = tool_context.state.get("confluence_rules", "")
        if skill.name not in existing_rules:
            skill_markdown = compile_skills_to_markdown([skill])
            if skill_markdown:
                separator = "\n\n---\n\n" if existing_rules else ""
                tool_context.state["confluence_rules"] = f"{existing_rules}{separator}{skill_markdown}".strip()

    instructions = getattr(skill, "instructions", "") or ""
    desc = getattr(skill, "description", "") or ""

    msg = (
        f"Successfully pulled GCP skill '{skill.name}' ({len(instructions)} chars of instructions, "
        f"{len(resource_files)} resource files). Ready for audit and compliance."
    )
    logger.info("pull_gcp_skill: %s", msg)

    return {
        "status": "success",
        "skill_name": skill.name,
        "description": desc,
        "instructions": instructions,
        "resources": resources_dict,
        "resource_files": resource_files,
        "message": msg,
    }


# Alias for backward compatibility & natural naming
fetch_gcp_skill = pull_gcp_skill


async def list_available_gcp_skills(
    query: str = "",
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Lists or searches available skills in the Google Cloud Skill Registry.

    Args:
        query: Optional search keyword to filter skills (e.g. 'prompt', 'inference', 'gke', 'security', 'waf').
               If omitted or empty, lists all skills discovered in the project.
        tool_context: Optional ADK ToolContext.

    Returns:
        A dict with:
          - "status": "success" or "error"
          - "total_skills": Number of skills found
          - "skills": List of dicts with 'name' and 'description'
          - "message": Human-readable status message
    """
    try:
        reg = get_gcp_skill_registry()
        if reg is None:
            return {
                "status": "error",
                "total_skills": 0,
                "skills": [],
                "message": "GCP Skill Registry is not initialized or unavailable.",
            }

        search_results = await reg.search_skills(query=query)
        skills_list = [
            {"name": fm.name, "description": fm.description}
            for fm in search_results
        ]

        return {
            "status": "success",
            "total_skills": len(skills_list),
            "skills": skills_list,
            "message": f"Found {len(skills_list)} GCP skills matching query '{query}'.",
        }
    except Exception as e:
        logger.error("list_available_gcp_skills: error searching skills: %s", e)
        return {
            "status": "error",
            "total_skills": 0,
            "skills": [],
            "message": f"Failed to list GCP skills: {e}",
        }


async def pull_multiple_gcp_skills(
    skill_names: Union[List[str], str],
    include_resources: bool = False,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Pulls multiple Google Cloud Platform (GCP) Skills in a single batch tool call.

    Args:
        skill_names: List of skill names or comma-separated string (e.g. ['agent-platform-prompt-management', 'agent-platform-inference']).
        include_resources: Whether to include bundled reference files in each skill payload.
        tool_context: Optional ADK ToolContext.

    Returns:
        A dict with:
          - "status": "success" or "error"
          - "loaded_count": Count of successfully pulled skills
          - "skills": List of individual skill pull results
          - "compiled_rules": Consolidated markdown rules for review/governance
          - "message": Human-readable summary message
    """
    if isinstance(skill_names, str):
        names_list = [n.strip() for n in skill_names.split(",") if n.strip()]
    elif isinstance(skill_names, (list, tuple, set)):
        names_list = [str(n).strip() for n in skill_names if str(n).strip()]
    else:
        names_list = []

    if not names_list:
        return {
            "status": "error",
            "loaded_count": 0,
            "skills": [],
            "compiled_rules": "",
            "message": "No valid skill names provided.",
        }

    results = []
    loaded_skills_objs = []

    for name in names_list:
        res = await pull_gcp_skill(skill_name=name, include_resources=include_resources, tool_context=tool_context)
        results.append(res)
        if res.get("status") == "success":
            skill_obj = await fetch_skill_by_name(name)
            if skill_obj is not None:
                loaded_skills_objs.append(skill_obj)

    compiled_markdown = compile_skills_to_markdown(loaded_skills_objs) if loaded_skills_objs else ""

    success_count = sum(1 for r in results if r.get("status") == "success")
    return {
        "status": "success" if success_count > 0 else "error",
        "loaded_count": success_count,
        "skills": results,
        "compiled_rules": compiled_markdown,
        "message": f"Successfully pulled {success_count}/{len(names_list)} GCP skills.",
    }
