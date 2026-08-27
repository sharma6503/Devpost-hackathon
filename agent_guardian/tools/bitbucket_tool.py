from __future__ import annotations

"""
Bitbucket Cloud REST API v2 ingestion tool.

Mirrors github_ingest_repository for Bitbucket Cloud repositories.
Auth: BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD (Basic auth).
"""

import asyncio
import logging
import os
from pathlib import PurePosixPath

import httpx

logger = logging.getLogger(__name__)

_BB_BASE = "https://api.bitbucket.org/2.0"


def _make_client() -> httpx.AsyncClient:
    """Return an AsyncClient with Bitbucket auth applied.

    Priority:
      1. BITBUCKET_TOKEN  → Bearer token (HTTP access token / workspace token)
         If the token is an Atlassian Scoped API Token (starts with ATATT),
         it must be used with Basic Auth using the Atlassian email address.
      2. BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD  → Basic auth
      3. No auth (public repos only — most private repos will 401)
    """
    token = os.environ.get("BITBUCKET_TOKEN", "").strip()
    if token:
        if token.startswith("ATATT"):
            # Atlassian Scoped API Tokens require Basic Auth with registered email
            email = (
                os.environ.get("ATLASSIAN_USERNAME", "").strip()
                or os.environ.get("BITBUCKET_USERNAME", "").strip()
            )
            return httpx.AsyncClient(
                auth=(email, token),
                follow_redirects=True,
            )
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=True,
        )
    user = os.environ.get("BITBUCKET_USERNAME", "").strip()
    pwd = os.environ.get("BITBUCKET_APP_PASSWORD", "").strip()
    if user and pwd:
        return httpx.AsyncClient(auth=(user, pwd), follow_redirects=True)
    return httpx.AsyncClient(follow_redirects=True)


def _has_credentials() -> bool:
    return bool(
        os.environ.get("BITBUCKET_TOKEN")
        or (os.environ.get("BITBUCKET_USERNAME") and os.environ.get("BITBUCKET_APP_PASSWORD"))
    )


async def _get_default_branch(client: httpx.AsyncClient, workspace: str, repo_slug: str) -> str:
    url = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}"
    resp = await client.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json().get("mainbranch", {}).get("name", "main")


async def _list_all_files(
    client: httpx.AsyncClient,
    workspace: str,
    repo_slug: str,
    ref: str,
) -> list[str]:
    """BFS walk of Bitbucket src API to enumerate all blob paths."""
    files: list[str] = []
    queue: list[str] = [""]
    visited: set[str] = set()

    while queue:
        batch, queue = queue[:20], queue[20:]
        tasks = [_list_dir(client, workspace, repo_slug, ref, d) for d in batch if d not in visited]
        for d in batch:
            visited.add(d)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.debug("bitbucket list dir error: %s", result)
                continue
            for entry in result:
                epath = entry.get("path", "")
                etype = entry.get("type", "")
                if not epath:
                    continue
                if etype == "commit_directory":
                    if epath not in visited:
                        queue.append(epath)
                elif etype == "commit_file":
                    files.append(epath)
    return files


async def _list_dir(
    client: httpx.AsyncClient,
    workspace: str,
    repo_slug: str,
    ref: str,
    path: str,
) -> list[dict]:
    entries: list[dict] = []
    url = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/src/{ref}/{path}"
    params: dict = {"pagelen": 100}
    while url:
        resp = await client.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        entries.extend(data.get("values", []))
        url = data.get("next")
        params = {}
    return entries


async def bitbucket_ingest_repository(
    workspace: str,
    repo_slug: str,
    ref: str = "",
) -> dict:
    """Deterministically ingest an entire Bitbucket Cloud repository.

    Args:
        workspace: Bitbucket workspace (user or team slug).
        repo_slug: Repository slug.
        ref: Branch, tag, or commit SHA. Empty = repo default branch.

    Returns:
        Same shape as github_ingest_repository:
        {status, codebase, files, skipped, total_files, fetched_files, truncated_tree, bytes}
    """
    from ..config import Config
    from .file_tool import in_skipped_dir, is_ingestible_file

    if not _has_credentials():
        return {
            "status": "error",
            "codebase": (
                "[INGESTION_FAILED] Bitbucket credentials missing. "
                "Set BITBUCKET_TOKEN (Bearer token) or both BITBUCKET_USERNAME "
                "and BITBUCKET_APP_PASSWORD in your .env."
            ),
            "files": [],
            "skipped": [],
            "total_files": 0,
            "fetched_files": 0,
            "truncated_tree": False,
            "bytes": 0,
        }

    _cfg = Config()
    budget = _cfg.max_repo_codebase_chars

    async with _make_client() as client:
        # 1. Resolve default branch if not specified.
        if not ref:
            try:
                ref = await _get_default_branch(client, workspace, repo_slug)
                logger.info("bitbucket_ingest_repository: default branch = %s", ref)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (401, 403):
                    msg = (
                        f"[INGESTION_FAILED] Bitbucket auth failed (HTTP {status}). "
                        "Check BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD."
                    )
                elif status == 404:
                    msg = (
                        f"[INGESTION_FAILED] Repository '{workspace}/{repo_slug}' not found "
                        f"on Bitbucket (HTTP 404). Verify the workspace and repo slug."
                    )
                else:
                    msg = f"[INGESTION_FAILED] HTTP {status} accessing '{workspace}/{repo_slug}'."
                return {
                    "status": "error",
                    "codebase": msg,
                    "files": [],
                    "skipped": [],
                    "total_files": 0,
                    "fetched_files": 0,
                    "truncated_tree": False,
                    "bytes": 0,
                }

        # 2. Enumerate all file paths.
        try:
            all_paths = await _list_all_files(client, workspace, repo_slug, ref)
        except Exception as e:
            return {
                "status": "error",
                "codebase": f"[INGESTION_FAILED] Failed to list repository tree: {e}",
                "files": [],
                "skipped": [],
                "total_files": 0,
                "fetched_files": 0,
                "truncated_tree": False,
                "bytes": 0,
            }

        # 3. Filter.
        eligible: list[str] = []
        skipped: list[dict] = []
        for p in all_paths:
            parts = PurePosixPath(p).parts
            if in_skipped_dir(parts):
                continue
            if not is_ingestible_file(p):
                skipped.append({"path": p, "reason": "binary/media (denylisted extension)"})
                continue
            eligible.append(p)

        # 4. Fetch blobs with bounded concurrency.
        sem = asyncio.Semaphore(16)

        async def _fetch_one(path: str):
            async with sem:
                url = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/src/{ref}/{path}"
                try:
                    resp = await client.get(url, timeout=20)
                    resp.raise_for_status()
                    return path, resp.text, None
                except httpx.HTTPStatusError as e:
                    return path, None, f"HTTP {e.response.status_code}"
                except Exception as e:
                    return path, None, e.__class__.__name__

        results = await asyncio.gather(*[_fetch_one(p) for p in eligible])

        # 5. Assemble.
        output: list[str] = []
        fetched: list[dict] = []
        total_chars = 0
        for path, content, err in results:
            if err:
                skipped.append({"path": path, "reason": err})
                continue
            block = f"--- {path} ---\n{content}"
            if total_chars + len(block) + 2 > budget:
                skipped.append({"path": path, "reason": "codebase ingest budget exceeded"})
                continue
            fetched.append({"path": path, "bytes": len(content)})
            output.append(block)
            total_chars += len(block) + 2

    codebase = "\n\n".join(output)
    if any(s["reason"] == "codebase ingest budget exceeded" for s in skipped):
        codebase += "\n\n[!] WARNING: Repository exceeded the ingest budget; some files were omitted."

    logger.info(
        "bitbucket_ingest_repository: %s/%s — fetched %d/%d eligible, %d skipped.",
        workspace,
        repo_slug,
        len(fetched),
        len(eligible),
        len(skipped),
    )

    return {
        "status": "ok",
        "codebase": codebase,
        "files": fetched,
        "skipped": skipped,
        "total_files": len(eligible),
        "fetched_files": len(fetched),
        "truncated_tree": False,
        "bytes": total_chars,
    }


async def bitbucket_create_branch(
    workspace: str,
    repo_slug: str,
    branch: str,
    from_branch: str = "main",
) -> dict:
    """Create a new branch in a Bitbucket repository from a source branch."""
    async with _make_client() as client:
        # First get the hash of the source branch
        try:
            url_branch = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/refs/branches/{from_branch}"
            resp_branch = await client.get(url_branch, timeout=15)
            resp_branch.raise_for_status()
            target_hash = resp_branch.json().get("target", {}).get("hash", "")
        except httpx.HTTPStatusError as e:
            # If from_branch is missing or fails, let's try master
            if from_branch == "main":
                try:
                    url_branch = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/refs/branches/master"
                    resp_branch = await client.get(url_branch, timeout=15)
                    resp_branch.raise_for_status()
                    target_hash = resp_branch.json().get("target", {}).get("hash", "")
                    from_branch = "master"
                except Exception:
                    return {"status": "error", "message": f"Source branch '{from_branch}' not found: {e}"}
            else:
                return {"status": "error", "message": f"Source branch '{from_branch}' not found: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

        # Now create the branch
        try:
            url_create = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/refs/branches"
            payload = {"name": branch, "target": {"hash": target_hash}}
            resp_create = await client.post(url_create, json=payload, timeout=15)
            # If it already exists (400 Bad Request with specific message), ignore and treat as OK
            if resp_create.status_code == 400 and "already exists" in resp_create.text:
                return {"status": "ok", "base_branch": from_branch}
            resp_create.raise_for_status()
            return {"status": "ok", "base_branch": from_branch}
        except Exception as e:
            # Double check if branch exists
            try:
                url_check = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/refs/branches/{branch}"
                resp_check = await client.get(url_check, timeout=10)
                if resp_check.status_code == 200:
                    return {"status": "ok", "base_branch": from_branch}
            except Exception:
                pass
            return {"status": "error", "message": str(e)}


async def bitbucket_commit_files(
    workspace: str,
    repo_slug: str,
    branch: str,
    commit_message: str,
    additions_and_modifications: dict[str, str],
    deletions: list[str],
) -> dict:
    """Commit multiple file additions, modifications, and deletions in a single request."""
    async with _make_client() as client:
        url = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/src"
        data = {
            "message": commit_message,
            "branch": branch,
        }
        multipart_files = []
        for path in deletions:
            multipart_files.append(("files", (None, path)))
        for path, content in additions_and_modifications.items():
            multipart_files.append((path, (os.path.basename(path), content, "text/plain")))

        try:
            resp = await client.post(url, data=data, files=multipart_files, timeout=30)
            resp.raise_for_status()
            return {"status": "ok"}
        except Exception as e:
            err_msg = str(e)
            if isinstance(e, httpx.HTTPStatusError):
                err_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            return {"status": "error", "message": err_msg}


async def bitbucket_create_pull_request(
    workspace: str,
    repo_slug: str,
    title: str,
    pr_branch: str,
    base_branch: str,
    description: str = "",
) -> dict:
    """Create a pull request on Bitbucket Cloud."""
    async with _make_client() as client:
        url = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/pullrequests"
        payload = {
            "title": title,
            "description": description,
            "source": {"branch": {"name": pr_branch}},
            "destination": {"branch": {"name": base_branch}},
        }
        try:
            resp = await client.post(url, json=payload, timeout=20)
            # If pull request already exists, find existing PR or return it
            if resp.status_code == 400 and "already exists" in resp.text:
                try:
                    url_search = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/pullrequests"
                    resp_search = await client.get(url_search, params={"state": "OPEN"}, timeout=15)
                    if resp_search.status_code == 200:
                        for pr in resp_search.json().get("values", []):
                            if pr.get("source", {}).get("branch", {}).get("name") == pr_branch:
                                return {
                                    "status": "ok",
                                    "pr_url": pr.get("links", {}).get("html", {}).get("href", ""),
                                    "number": pr.get("id", 0),
                                }
                except Exception:
                    pass
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "pr_url": data.get("links", {}).get("html", {}).get("href", ""),
                "number": data.get("id", 0),
            }
        except Exception as e:
            err_msg = str(e)
            if isinstance(e, httpx.HTTPStatusError):
                err_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            return {"status": "error", "message": err_msg}


async def bitbucket_apply_remediation_plan(
    plan: dict | None = None,
    workspace: str = "",
    repo_slug: str = "",
    base_branch: str = "",
    pr_branch: str = "",
    tool_context=None,
) -> dict:
    """Deterministically apply a RemediationPlan and open a Bitbucket PR — no LLM merging."""
    import json

    raw = plan
    if raw is None and tool_context is not None:
        raw = (getattr(tool_context, "state", {}) or {}).get("remediation_plan", "")

    if hasattr(raw, "model_dump") and callable(raw.model_dump):
        plan = raw.model_dump()
    elif hasattr(raw, "dict") and callable(raw.dict):
        plan = raw.dict()
    elif isinstance(raw, str) and raw.strip():
        try:
            plan = json.loads(raw)
        except Exception:
            plan = None
    elif isinstance(raw, dict):
        plan = raw
    else:
        plan = None

    if not isinstance(plan, dict):
        return {"status": "error", "message": "No usable remediation plan available.", "committed": [], "failed": []}

    # Resolve workspace and repo_slug with fallbacks
    if not workspace or not repo_slug:
        target = str(plan.get("target_repo") or "").strip()
        if "/" in target and target.lower() != "workspace/repo":
            t_workspace, _, t_repo_slug = target.partition("/")
            workspace = workspace or t_workspace.strip()
            repo_slug = repo_slug or t_repo_slug.strip()

    if (not workspace or not repo_slug) and tool_context is not None:
        state = getattr(tool_context, "state", {}) or {}
        st_ws = str(state.get("authorized_bitbucket_workspace") or state.get("bitbucket_workspace") or "").strip()
        st_slug = str(state.get("authorized_bitbucket_repo_slug") or state.get("bitbucket_repo_slug") or "").strip()
        workspace = workspace or st_ws
        repo_slug = repo_slug or st_slug
        if not workspace or not repo_slug:
            repo_name = str(state.get("repo_name") or "").strip()
            if "/" in repo_name and repo_name.lower() != "workspace/repo":
                t_ws, _, t_slug = repo_name.partition("/")
                workspace = workspace or t_ws.strip()
                repo_slug = repo_slug or t_slug.strip()

    base_branch = base_branch or str(plan.get("base_branch") or "main")
    pr_branch = pr_branch or str(plan.get("pr_branch") or "agent_guardian/review")

    if not workspace or not repo_slug:
        return {
            "status": "error",
            "message": "Could not resolve Bitbucket workspace/repo_slug from plan or state.",
            "committed": [],
            "failed": [],
        }

    changes = plan.get("changes", []) or []

    # 1. Create the PR branch (idempotent).
    br = await bitbucket_create_branch(workspace, repo_slug, pr_branch, base_branch)
    if br.get("status") != "ok":
        return {
            "status": "error",
            "message": f"Branch creation failed: {br.get('message')}",
            "committed": [],
            "failed": [],
        }
    base_branch = str(br.get("base_branch") or base_branch)

    committed: list[dict] = []
    failed: list[dict] = []
    additions_and_modifications: dict[str, str] = {}
    deletions: list[str] = []

    # Import helper logic from github_tool
    from .github_tool import _merge_modify, _validate_syntax

    async with _make_client() as client:
        for ch in changes:
            fid = ch.get("finding_id", "?")
            fpath = str(ch.get("file_path") or "").strip().replace("\\", "/")
            ctype = (ch.get("change_type") or "modify").lower()

            if not fpath:
                failed.append({"finding_id": fid, "file_path": fpath, "reason": "missing file_path"})
                continue

            try:
                if ctype == "create":
                    content = ch.get("replacement_snippet") or ""
                    is_valid, syn_err = _validate_syntax(fpath, content)
                    if not is_valid:
                        failed.append({"finding_id": fid, "file_path": fpath, "reason": syn_err})
                        continue
                    additions_and_modifications[fpath] = content
                    committed.append({"finding_id": fid, "file_path": fpath, "change_type": ctype})
                elif ctype == "delete":
                    deletions.append(fpath)
                    committed.append({"finding_id": fid, "file_path": fpath, "change_type": ctype})
                else:  # modify
                    # If this file was already created or modified in this same plan batch, chain off the in-memory content
                    if fpath in additions_and_modifications:
                        cur_content = additions_and_modifications[fpath]
                    else:
                        try:
                            url = f"{_BB_BASE}/repositories/{workspace}/{repo_slug}/src/{base_branch}/{fpath}"
                            resp = await client.get(url, timeout=20)
                            resp.raise_for_status()
                            cur_content = resp.text
                        except Exception as fe:
                            failed.append(
                                {
                                    "finding_id": fid,
                                    "file_path": fpath,
                                    "reason": f"could not fetch file: {fe.__class__.__name__}",
                                }
                            )
                            continue
                    merged, err = _merge_modify(cur_content, ch.get("original_snippet"), ch.get("replacement_snippet"))
                    if err:
                        failed.append({"finding_id": fid, "file_path": fpath, "reason": err})
                        continue
                    is_valid, syn_err = _validate_syntax(fpath, merged)
                    if not is_valid:
                        failed.append({"finding_id": fid, "file_path": fpath, "reason": syn_err})
                        continue
                    additions_and_modifications[fpath] = merged
                    committed.append({"finding_id": fid, "file_path": fpath, "change_type": ctype})
            except Exception as e:
                failed.append({"finding_id": fid, "file_path": fpath, "reason": f"{e.__class__.__name__}: {e}"})

    if not committed:
        return {
            "status": "error",
            "message": "No changes could be applied (all failed exact-match verification or commit).",
            "committed": [],
            "failed": failed,
            "pr_url": "",
        }

    # 2. Commit files to Bitbucket
    commit_id = str((getattr(tool_context, "state", {}) or {}).get("remediation_commit_id", "")).strip()
    prefix = f"{commit_id}: " if commit_id and commit_id.lower() not in ("none", "null") else ""
    commit_msg = f"{prefix}[Agent Guardian] Automated remediation\n\nPlan with {len(committed)} changes"
    commit_res = await bitbucket_commit_files(
        workspace, repo_slug, pr_branch, commit_msg, additions_and_modifications, deletions
    )
    if commit_res.get("status") != "ok":
        return {
            "status": "error",
            "message": f"Commit failed: {commit_res.get('message')}",
            "committed": [],
            "failed": failed,
            "pr_url": "",
        }

    # 3. Open the PR on Bitbucket
    pr = await bitbucket_create_pull_request(
        workspace,
        repo_slug,
        plan.get("pr_title") or "[Agent Guardian] Automated remediation",
        pr_branch,
        base_branch,
        plan.get("pr_body") or "Automated remediation by Agent Guardian.",
    )
    if pr.get("status") == "ok":
        return {
            "status": "ok",
            "pr_url": pr.get("pr_url", ""),
            "pr_number": pr.get("number", 0),
            "committed": committed,
            "failed": failed,
            "branch": pr_branch,
            "message": "PR opened successfully.",
        }
    else:
        return {
            "status": "error",
            "message": f"PR creation failed: {pr.get('message')}",
            "committed": committed,
            "failed": failed,
            "pr_url": "",
        }
