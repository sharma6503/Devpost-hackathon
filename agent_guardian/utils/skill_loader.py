from __future__ import annotations

"""
skill_loader.py — GCP Skill Registry integration, local skill discovery, and formatting for Agent Guardian.

Integrates with Google Cloud Skill Registry (GCPSkillRegistry) and ADK's SkillToolset.
Supports:
1. Dynamic remote skill discovery, search, and retrieval from GCPSkillRegistry.
2. Local filesystem skill discovery and loading via ADK's `load_skills_from_dir` / `load_skill_from_dir`.
3. User-configured skills via environment variables (`GCP_SKILLS` / `SKILLS` / `SKILLS_DIR`).
4. Automatic markdown compilation and integration with Confluence governance rules.
5. Construction of ADK `SkillToolset` for parallel review experts, followup agent, and root orchestrator.
"""

import os
import re
import asyncio
import logging
import pathlib
from typing import List, Dict, Tuple, Optional, Union, Any
from google.adk.skills.models import Skill, Frontmatter
from google.adk.skills.skill_registry import SkillRegistry
from google.adk.integrations.skill_registry import GCPSkillRegistry
from google.adk.tools.skill_toolset import SkillToolset

try:
    from google.adk.skills import load_skills_from_dir, load_skill_from_dir
    _ADK_SKILLS_FS_AVAILABLE = True
except ImportError:
    _ADK_SKILLS_FS_AVAILABLE = False
    load_skills_from_dir = None
    load_skill_from_dir = None

logger = logging.getLogger(__name__)

# Cache: skill_name -> Skill object
_GCP_SKILL_CACHE: Dict[str, Skill] = {}

# Cache: (name, description) tuple fingerprint -> compiled markdown string.
_MARKDOWN_CACHE: Dict[Tuple, str] = {}

# Cache: cache_key -> SkillToolset instance
_TOOLSET_CACHE: Dict[str, SkillToolset] = {}


def normalize_skill_name(raw_name: str) -> str:
    """Sanitize and normalize a skill name to match ADK kebab/snake case requirements.

    Handles:
    - Full GCP resource paths: 'projects/123/locations/us-central1/skills/my-skill' -> 'my-skill'
    - File paths / URLs: 'skills/my-skill/SKILL.md' -> 'my-skill'
    - Whitespace and quotes: " 'my-skill' " -> 'my-skill'
    - Uppercase and spaces: 'My Skill' -> 'my-skill'
    """
    if not raw_name:
        return ""
    cleaned = raw_name.strip().strip("'\"")
    # If full GCP resource path or file path
    if "/" in cleaned or "\\" in cleaned:
        cleaned = cleaned.replace("\\", "/").rstrip("/")
        if cleaned.lower().endswith("/skill.md"):
            cleaned = cleaned.rsplit("/", 2)[-2]
        else:
            cleaned = cleaned.rsplit("/", 1)[-1]
    cleaned = cleaned.strip().lower()
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    cleaned = re.sub(r"[^a-z0-9\-_]", "", cleaned)
    return cleaned


def get_configured_skill_names() -> List[str]:
    """Return the list of skill names configured via environment variables.

    Reads from `GCP_SKILLS` or `SKILLS` (comma-separated, semicolon-separated, or newline-separated).
    Example: GCP_SKILLS="governance-audit, implementation-standards" -> ["governance-audit", "implementation-standards"]
    """
    raw = os.environ.get("GCP_SKILLS") or os.environ.get("SKILLS") or ""
    if not raw:
        return []

    # Handle commas, semicolons, and newlines
    normalized = raw.replace(";", ",").replace("\n", ",")
    names: List[str] = []
    for s in normalized.split(","):
        clean = normalize_skill_name(s)
        if clean and clean not in names:
            names.append(clean)
    return names


def get_gcp_skill_registry(
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    credentials: Optional[Any] = None,
) -> Optional[GCPSkillRegistry]:
    """Instantiate a Google Cloud Skill Registry client.

    Reads project and location from environment if not explicitly provided.
    Normalizes environment variables (GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION).
    Returns None if project_id is unavailable or if construction fails.
    """
    proj = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    loc = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_REGION") or "us-central1"
    if not proj:
        logger.debug("get_gcp_skill_registry: GOOGLE_CLOUD_PROJECT not set, registry disabled.")
        return None

    # Synchronize environment variables for ADK and underlying GCP SDKs
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", proj)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", loc)

    try:
        registry = GCPSkillRegistry(project_id=proj, location=loc, credentials=credentials)
        logger.info("get_gcp_skill_registry: GCPSkillRegistry initialized (project=%s, location=%s)", proj, loc)
        return registry
    except Exception as e:
        logger.warning("get_gcp_skill_registry: failed to initialize GCPSkillRegistry: %s", e)
        return None


def load_local_skills(
    skills_dir: Optional[Union[str, pathlib.Path]] = None,
) -> List[Skill]:
    """Discover and load local skills from filesystem directories.

    Scans:
    1. Explicit `skills_dir` parameter if passed.
    2. Environment variable `SKILLS_DIR` if set.
    3. Project root `./skills` directory.
    4. Package `agent_guardian/skills` directory.

    Returns:
        List of loaded Skill objects, populated into `_GCP_SKILL_CACHE`.
    """
    if not _ADK_SKILLS_FS_AVAILABLE:
        logger.debug("load_local_skills: ADK filesystem skill loaders not available.")
        return []

    candidate_dirs: List[pathlib.Path] = []
    if skills_dir:
        candidate_dirs.append(pathlib.Path(skills_dir))

    env_dir = os.environ.get("SKILLS_DIR")
    if env_dir:
        candidate_dirs.append(pathlib.Path(env_dir))

    # Standard project paths
    cwd_skills = pathlib.Path.cwd() / "skills"
    if cwd_skills not in candidate_dirs:
        candidate_dirs.append(cwd_skills)

    pkg_skills = pathlib.Path(__file__).resolve().parent.parent / "skills"
    if pkg_skills not in candidate_dirs:
        candidate_dirs.append(pkg_skills)

    loaded_skills: List[Skill] = []
    for d in candidate_dirs:
        if not d.exists() or not d.is_dir():
            continue

        try:
            # If the directory itself is a skill (contains SKILL.md)
            if (d / "SKILL.md").exists() and load_skill_from_dir is not None:
                try:
                    skill = load_skill_from_dir(d)
                    if skill and skill.name not in _GCP_SKILL_CACHE:
                        _GCP_SKILL_CACHE[skill.name] = skill
                        loaded_skills.append(skill)
                        logger.info("Loaded local skill: '%s' from %s", skill.name, d)
                except Exception as ex:
                    logger.debug("Failed loading single skill from %s: %s", d, ex)

            # If the directory contains subdirectories of skills
            if load_skills_from_dir is not None:
                dir_skills = load_skills_from_dir(d)
                for skill in dir_skills:
                    if skill and skill.name not in _GCP_SKILL_CACHE:
                        _GCP_SKILL_CACHE[skill.name] = skill
                        loaded_skills.append(skill)
                        logger.info("Loaded local skill: '%s' from %s", skill.name, d)

            # Also check 1-level deep subdirectories if directory itself has nested skill groups (e.g. skills/cloud/*)
            for sub in d.iterdir():
                if sub.is_dir() and (sub / "SKILL.md").exists() and load_skill_from_dir is not None:
                    try:
                        skill = load_skill_from_dir(sub)
                        if skill and skill.name not in _GCP_SKILL_CACHE:
                            _GCP_SKILL_CACHE[skill.name] = skill
                            loaded_skills.append(skill)
                            logger.info("Loaded local nested skill: '%s' from %s", skill.name, sub)
                    except Exception as sub_ex:
                        logger.debug("Failed loading nested skill from %s: %s", sub, sub_ex)
        except Exception as e:
            logger.debug("Failed loading skills from directory %s: %s", d, e)

    return loaded_skills


async def _fetch_gcp_skill_direct(
    skill_ref: str,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
) -> Optional[Skill]:
    """Fetch skill directly via GCP Agent Registry REST API.
    
    Handles:
    - Full resource names (projects/.../skills/...)
    - Domain prefixed names (e.g. cloud.google.com-agent-platform-prompt-management)
    - Short display names (e.g. agent-platform-prompt-management)
    - Follows signed GCS download redirects for skill zip payloads.
    """
    proj = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    loc = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_REGION") or "global"
    if not proj:
        return None

    try:
        import google.auth
        from google.auth.transport import requests as auth_requests
        import httpx
        from google.adk.skills import _utils
    except ImportError:
        return None

    try:
        credentials, _ = google.auth.default()
        if not credentials.valid:
            req = auth_requests.Request()
            await asyncio.to_thread(credentials.refresh, req)

        quota_project_id = getattr(credentials, "quota_project_id", None) or proj
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        }
        if quota_project_id:
            headers["x-goog-user-project"] = quota_project_id

        base_url = os.environ.get("AGENT_REGISTRY_ENDPOINT", "https://agentregistry.googleapis.com/v1alpha")

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            data = None
            # 1. Direct GET if full resource path or exact ID
            if skill_ref.startswith("projects/"):
                skill_url = f"{base_url}/{skill_ref}"
                resp = await client.get(skill_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
            else:
                skill_url = f"{base_url}/projects/{proj}/locations/{loc}/skills/{skill_ref}"
                resp = await client.get(skill_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()

            # 2. If not found, list skills in project and match by displayName or suffix
            if not data:
                list_url = f"{base_url}/projects/{proj}/locations/{loc}/skills"
                list_resp = await client.get(list_url, headers=headers)
                if list_resp.status_code == 200:
                    for s in list_resp.json().get("skills", []):
                        s_name = s.get("name", "")
                        s_display = s.get("displayName", "")
                        s_id = s_name.split("/")[-1] if "/" in s_name else s_name
                        clean_ref = normalize_skill_name(skill_ref)
                        if (
                            skill_ref == s_name
                            or skill_ref == s_id
                            or skill_ref == s_display
                            or clean_ref == normalize_skill_name(s_display)
                            or clean_ref == normalize_skill_name(s_id)
                            or s_id.endswith(f"-{skill_ref}")
                            or s_id.endswith(f".{skill_ref}")
                            or s_id.endswith(f"-{clean_ref}")
                        ):
                            data = s
                            break

            if not data:
                return None

            rev = data.get("defaultRevision") or data.get("default_revision")
            if not rev:
                return None

            rev_url = f"{base_url}/{rev}" if not rev.startswith("http") else rev
            media_resp = await client.get(rev_url, headers=headers, params={"alt": "media"})
            if media_resp.status_code != 200:
                logger.warning("_fetch_gcp_skill_direct: media download failed (%s) for %s", media_resp.status_code, rev)
                return None

            skill = await asyncio.to_thread(_utils._load_skill_from_zip_bytes, media_resp.content)
            if skill:
                skill._uri = rev_url
                logger.info("_fetch_gcp_skill_direct: successfully loaded GCP skill '%s' (rev: %s)", skill.name, rev)
                return skill
    except Exception as e:
        logger.debug("_fetch_gcp_skill_direct: error fetching '%s': %s", skill_ref, e)
        return None

    return None


async def fetch_skill_by_name(
    skill_name: str,
    registry: Optional[GCPSkillRegistry] = None,
    use_cache: bool = True,
) -> Optional[Skill]:
    """Fetch a single skill from GCP Skill Registry or local fallback cache.

    Args:
        skill_name: Raw or normalized skill name (e.g. 'agent-platform-prompt-management' or full GCP path).
        registry: Optional GCPSkillRegistry instance.
        use_cache: Whether to use cached skill instances.

    Returns:
        Skill object if found, or None.
    """
    name = normalize_skill_name(skill_name)
    if not name and not skill_name:
        return None

    cache_key = name or skill_name
    if use_cache and cache_key in _GCP_SKILL_CACHE:
        return _GCP_SKILL_CACHE[cache_key]
    if use_cache and skill_name in _GCP_SKILL_CACHE:
        return _GCP_SKILL_CACHE[skill_name]

    # 1. Direct GCP REST resolution (handles domain prefixes like cloud.google.com-...)
    direct_skill = await _fetch_gcp_skill_direct(skill_name)
    if direct_skill is not None:
        if use_cache:
            _GCP_SKILL_CACHE[direct_skill.name] = direct_skill
            if name:
                _GCP_SKILL_CACHE[name] = direct_skill
            _GCP_SKILL_CACHE[skill_name] = direct_skill
        return direct_skill

    # 2. GCPSkillRegistry SDK get_skill fallback
    reg = registry or get_gcp_skill_registry()
    if reg is not None and name:
        try:
            logger.info("fetch_skill_by_name: fetching '%s' from GCPSkillRegistry...", name)
            skill = await reg.get_skill(name=name)
            if skill is not None:
                if use_cache:
                    _GCP_SKILL_CACHE[name] = skill
                    _GCP_SKILL_CACHE[skill.name] = skill
                logger.info("fetch_skill_by_name: successfully fetched '%s' from GCP Skill Registry", name)
                return skill
        except Exception as e:
            logger.warning("fetch_skill_by_name: failed to fetch '%s' from GCPSkillRegistry: %s", name, e)

    # 3. Local filesystem fallback check
    load_local_skills()
    if name in _GCP_SKILL_CACHE:
        return _GCP_SKILL_CACHE[name]

    # 4. Additional directory check
    if _ADK_SKILLS_FS_AVAILABLE and load_skill_from_dir is not None and name:
        search_dirs = []
        env_dir = os.environ.get("SKILLS_DIR")
        if env_dir:
            search_dirs.append(pathlib.Path(env_dir))
        search_dirs.extend([
            pathlib.Path.cwd() / "skills",
            pathlib.Path(__file__).resolve().parent.parent / "skills",
        ])
        for base_dir in search_dirs:
            skill_path = base_dir / name
            if skill_path.exists() and (skill_path / "SKILL.md").exists():
                try:
                    skill = load_skill_from_dir(skill_path)
                    if skill:
                        if use_cache:
                            _GCP_SKILL_CACHE[name] = skill
                        return skill
                except Exception:
                    pass

    return None


async def search_gcp_skills(
    query: str,
    registry: Optional[GCPSkillRegistry] = None,
) -> List[Frontmatter]:
    """Search for skills in the GCP Skill Registry using a query string.

    Args:
        query: Semantic or keyword search query (e.g. 'governance', 'security', 'adk', 'cloud', 'prompt').
        registry: Optional GCPSkillRegistry instance.

    Returns:
        List of Frontmatter objects found in the registry.
    """
    if not query or not query.strip():
        return []

    query_str = query.strip().lower()

    # 1. GCPSkillRegistry SDK search_skills
    reg = registry or get_gcp_skill_registry()
    if reg is not None:
        try:
            logger.info("search_gcp_skills: searching GCP Skill Registry for '%s'...", query)
            results = await reg.search_skills(query=query.strip())
            if results:
                logger.info("search_gcp_skills: found %d skill(s) for query '%s'", len(results), query)
                return results
        except Exception as e:
            logger.debug("search_gcp_skills: GCPSkillRegistry search failed: %s", e)

    # 2. Direct GCP REST search/list
    proj = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    loc = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_REGION") or "global"
    if proj:
        try:
            import google.auth
            from google.auth.transport import requests as auth_requests
            import httpx

            credentials, _ = google.auth.default()
            if not credentials.valid:
                req = auth_requests.Request()
                await asyncio.to_thread(credentials.refresh, req)

            headers = {
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
                "x-goog-user-project": proj,
            }
            base_url = os.environ.get("AGENT_REGISTRY_ENDPOINT", "https://agentregistry.googleapis.com/v1alpha")
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                list_url = f"{base_url}/projects/{proj}/locations/{loc}/skills"
                resp = await client.get(list_url, headers=headers)
                if resp.status_code == 200:
                    skills_data = resp.json().get("skills", [])
                    matched: List[Frontmatter] = []
                    for s in skills_data:
                        s_name = s.get("name", "").split("/")[-1]
                        s_display = s.get("displayName", "")
                        s_desc = s.get("description", "") or ""
                        if (
                            not query_str
                            or query_str in s_name.lower()
                            or query_str in s_display.lower()
                            or query_str in s_desc.lower()
                        ):
                            matched.append(
                                Frontmatter(
                                    name=s_display or s_name,
                                    description=s_desc,
                                )
                            )
                    if matched:
                        logger.info("search_gcp_skills: found %d skill(s) via direct project listing", len(matched))
                        return matched
        except Exception as e:
            logger.debug("search_gcp_skills: direct list fallback failed: %s", e)

    return []


async def search_and_fetch_gcp_skills(
    query: str,
    registry: Optional[GCPSkillRegistry] = None,
    limit: int = 5,
    use_cache: bool = True,
) -> List[Skill]:
    """Search the GCP Skill Registry and fetch the full Skill objects.

    Args:
        query: Semantic or keyword search query.
        registry: Optional GCPSkillRegistry instance.
        limit: Maximum number of skills to fetch.
        use_cache: Whether to use cached skill instances.

    Returns:
        List of loaded Skill objects.
    """
    reg = registry or get_gcp_skill_registry()
    if reg is None:
        return []

    frontmatters = await search_gcp_skills(query, registry=reg)
    skills: List[Skill] = []
    for fm in frontmatters[:limit]:
        skill_name = getattr(fm, "name", None) or str(fm)
        skill = await fetch_skill_by_name(skill_name, registry=reg, use_cache=use_cache)
        if skill is not None:
            skills.append(skill)
    return skills


async def fetch_configured_gcp_skills(
    skill_names: Optional[List[str]] = None,
    registry: Optional[GCPSkillRegistry] = None,
    use_cache: bool = True,
    search_queries: Optional[List[str]] = None,
) -> List[Skill]:
    """Fetch the configured skills from Google Cloud Skill Registry or local fallback.

    Args:
        skill_names: Optional list of skill names. Defaults to `get_configured_skill_names()`.
        registry: Optional GCPSkillRegistry instance. Defaults to `get_gcp_skill_registry()`.
        use_cache: Whether to use cached skill instances.
        search_queries: Optional search queries to discover relevant skills if explicit names are empty.

    Returns:
        List of fetched Skill objects.
    """
    # Load any local skills first
    load_local_skills()

    names = skill_names if skill_names is not None else get_configured_skill_names()
    reg = registry or get_gcp_skill_registry()

    # If no explicit names configured, check if dynamic search queries are provided
    if not names and search_queries and reg is not None:
        for query in search_queries:
            discovered = await search_and_fetch_gcp_skills(query, registry=reg, use_cache=use_cache)
            for skill in discovered:
                if skill.name not in _GCP_SKILL_CACHE:
                    _GCP_SKILL_CACHE[skill.name] = skill

    if not names:
        # Return all currently discovered and cached skills
        return list(_GCP_SKILL_CACHE.values())

    skills: List[Skill] = []
    for raw_name in names:
        name = normalize_skill_name(raw_name)
        if not name:
            continue

        skill = await fetch_skill_by_name(name, registry=reg, use_cache=use_cache)
        if skill is not None:
            if skill not in skills:
                skills.append(skill)
        else:
            logger.warning(
                "fetch_configured_gcp_skills: skill '%s' not found in GCP registry or local paths.",
                name,
            )

    return skills


def compile_skills_to_markdown(skills: List[Skill]) -> str:
    """Compile Skill objects into a structured Markdown standards document for review experts."""
    if not skills:
        return ""

    fingerprint = tuple((s.name, getattr(s, "description", "") or "") for s in skills)
    if fingerprint in _MARKDOWN_CACHE:
        return _MARKDOWN_CACHE[fingerprint]

    markdown_parts: List[str] = []
    markdown_parts.append("=== 🛠️ GCP SKILLS REGISTRY STANDARDS & PLAYBOOKS ===")
    markdown_parts.append(
        "The following authoritative skills and standards were retrieved from the Skill Registry "
        "and must be strictly enforced during the review process.\n"
    )

    for skill in skills:
        markdown_parts.append(f"### Skill: {skill.name}")
        description = getattr(skill, "description", "") or getattr(getattr(skill, "frontmatter", None), "description", "")
        if description:
            markdown_parts.append(f"**Description**: {description}")

        markdown_parts.append("\n**Core Instructions & Scoring Criteria**:")
        if skill.instructions and skill.instructions.strip():
            markdown_parts.append(skill.instructions.strip())
        else:
            markdown_parts.append("*(No specific instructions provided)*")

        # Compile references (supporting both str and decoded bytes)
        resources = getattr(skill, "resources", None)
        references = getattr(resources, "references", None) or {}
        seen_bodies: set = set()
        emitted_any_ref = False
        for ref_name, ref_content in references.items():
            if isinstance(ref_content, bytes):
                ref_text = ref_content.decode("utf-8", errors="replace").strip()
            elif isinstance(ref_content, str):
                ref_text = ref_content.strip()
            else:
                continue

            if not ref_text or ref_text in seen_bodies:
                continue
            seen_bodies.add(ref_text)
            if not emitted_any_ref:
                markdown_parts.append("\n**Reference Materials**:")
                emitted_any_ref = True
            markdown_parts.append(f"#### Reference File: `references/{ref_name}`\n")
            markdown_parts.append(ref_text)
            markdown_parts.append("")

        # Compile assets list if any
        assets = getattr(resources, "assets", None) or {}
        if assets:
            markdown_parts.append("\n**Available Assets**:")
            for asset_name in assets.keys():
                markdown_parts.append(f"- `assets/{asset_name}`")

        markdown_parts.append("\n" + "-" * 40 + "\n")

    result = "\n".join(markdown_parts)
    _MARKDOWN_CACHE[fingerprint] = result
    return result


async def get_merged_ruleset(
    confluence_rules: str,
    skills: Optional[List[Skill]] = None,
    skill_names: Optional[List[str]] = None,
    search_queries: Optional[List[str]] = None,
) -> str:
    """Merge GCP Skill Registry standards with the base Confluence ruleset.

    Args:
        confluence_rules: Base ruleset text (e.g. from Confluence).
        skills: Optional pre-fetched Skill list.
        skill_names: Optional skill names to fetch if skills list is not provided.
        search_queries: Optional search queries to discover relevant skills.

    Returns:
        The combined ruleset string.
    """
    if skills is None:
        skills = await fetch_configured_gcp_skills(
            skill_names=skill_names,
            search_queries=search_queries,
        )

    if not skills:
        return confluence_rules

    compiled_skills = compile_skills_to_markdown(skills)

    base_clean = (confluence_rules or "").strip()
    if not base_clean or base_clean.startswith("[CONFLUENCE_UNAVAILABLE]"):
        return compiled_skills

    return f"{base_clean}\n\n{compiled_skills}"


def get_skill_toolset(
    skills: Optional[List[Skill]] = None,
    use_registry: bool = True,
    use_cache: bool = True,
) -> SkillToolset:
    """Construct an ADK SkillToolset with GCP Skill Registry.

    Args:
        skills: Preloaded Skill objects. If None, discovers local & cached skills.
        use_registry: Whether to attach GCPSkillRegistry for dynamic remote skill search/loading.
        use_cache: Whether to return a cached SkillToolset instance.

    Returns:
        A configured SkillToolset instance equipped with skill search, load, and execution tools.
    """
    # Ensure local skills are populated
    load_local_skills()

    proj = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or ""
    loc = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_REGION") or "us-central1"
    cache_key = f"{len(skills or [])}:{use_registry}:{proj}:{loc}"
    if use_cache and cache_key in _TOOLSET_CACHE:
        return _TOOLSET_CACHE[cache_key]

    loaded_skills = list(skills) if skills is not None else list(_GCP_SKILL_CACHE.values())
    registry: Optional[SkillRegistry] = get_gcp_skill_registry(project_id=proj, location=loc) if use_registry else None

    toolset = SkillToolset(
        skills=loaded_skills,
        registry=registry,
    )
    if use_cache:
        _TOOLSET_CACHE[cache_key] = toolset
    return toolset


def invalidate_skill_toolsets() -> None:
    """Clear cached skills, toolsets, and markdown compilations."""
    _GCP_SKILL_CACHE.clear()
    _MARKDOWN_CACHE.clear()
    _TOOLSET_CACHE.clear()

