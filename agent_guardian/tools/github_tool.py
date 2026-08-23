from __future__ import annotations

"""
GitHub REST API fallback tool.

Used when the GitHub MCP server (npx @modelcontextprotocol/server-github) is
unavailable (e.g. Node.js not installed). Provides basic read-only access to
GitHub repositories using the REST v3 API via the requests library.
"""

import os
import json
import base64
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)


def _headers() -> dict:
    """Build GitHub request headers, reading GITHUB_TOKEN fresh on every call.

    The token must NOT be snapshotted at import time: this module is pulled into
    the import graph before ``load_dotenv()`` runs in ``agent_guardian.agent``,
    so an import-time read returns an empty token, drops the Authorization
    header, and GitHub answers 404 (not 403) for private repos — surfacing as a
    spurious "branch could not be created (HTTP 404)".
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


from agent_guardian.utils.ipynb_utils import preprocess_ipynb_content


def _preprocess_ipynb(raw_json: str) -> str:
    """Extracts code and markdown cells from a Jupyter Notebook JSON string.
    Delegates to the central utility.
    """
    return preprocess_ipynb_content(raw_json)


async def github_get_file_contents(
    owner: str,
    repo: str,
    path: str,
    ref: str = "HEAD",
) -> dict:
    """Fetch the contents of a single file from a GitHub repository (Async).

    Args:
        owner: The GitHub organisation or username (e.g. "google").
        repo: The repository name (e.g. "adk-samples").
        path: The file path inside the repository.
        ref: The branch, tag, commit. Defaults to "HEAD".

    Returns:
        A dict with keys: "content", "path", "status".
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            resp = await client.get(url, params={"ref": ref}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            else:
                content = data.get("content", "")

            if path.lower().endswith(".ipynb"):
                content = _preprocess_ipynb(content)

            return {
                "status": "ok",
                "path": path,
                "content": content,
                "sha": data.get("sha"),
            }
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} fetching '{path}'"
            logger.error(f"GitHub Error: {msg} — {e}")
            return {
                "status": "error",
                "path": path,
                "content": f"[SYSTEM ERROR: {msg}]",
            }
        except Exception as e:
            logger.error(f"GitHub Error fetching '{path}': {e}")
            return {
                "status": "error",
                "path": path,
                "content": f"[SYSTEM ERROR: Failed to fetch {os.path.basename(path)}]",
            }


async def github_list_directory_contents(
    owner: str,
    repo: str,
    path: str = "",
    ref: str = "HEAD",
) -> dict:
    """List files and directories at a path within a GitHub repository (Async).

    Args:
        owner: The GitHub organisation or username (e.g. "google").
        repo: The repository name.
        path: Directory path. Empty means root.
        ref: The branch, tag, commit. Defaults to "HEAD".

    Returns:
        A dict with keys: "entries", "status", "message".
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            resp = await client.get(url, params={"ref": ref}, timeout=15)
            resp.raise_for_status()
            items = resp.json()
            if not isinstance(items, list):
                return {
                    "status": "ok",
                    "entries": [{"name": items["name"], "type": "file", "path": items["path"]}],
                }
            entries = [
                {
                    "name": i["name"],
                    "type": "dir" if i["type"] == "dir" else "file",
                    "path": i["path"],
                }
                for i in items
            ]
            return {"status": "ok", "entries": entries}
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} listing '{path or 'root'}'"
            logger.error(f"GitHub Error: {msg}")
            return {
                "status": "error",
                "entries": [],
                "message": f"[SYSTEM ERROR: {msg}]",
            }
        except Exception as e:
            logger.error(f"GitHub Error listing '{path or 'root'}': {e}")
            return {
                "status": "error",
                "entries": [],
                "message": f"[SYSTEM ERROR: Failed to list {os.path.basename(path) or 'root'}]",
            }


async def github_get_multiple_files(
    owner: str,
    repo: str,
    paths: list[str],
    ref: str = "HEAD",
) -> str:
    """Fetch the contents of multiple files from GitHub in parallel.

    Args:
        owner: The GitHub organisation or username.
        repo: The repository name.
        paths: List of file paths inside the repository.
        ref: The branch, tag, commit. Defaults to "HEAD".

    Returns:
        A consolidated string formatted with '--- <path> ---' separators.
    """
    if not paths:
        return "No paths provided."

    from ..config import Config

    _cfg = Config()

    async def _fetch(client: httpx.AsyncClient, path: str):
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        try:
            resp = await client.get(url, params={"ref": ref}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            else:
                content = data.get("content", "")
            return path, content
        except Exception as e:
            msg = f"Read error for '{os.path.basename(path)}'"
            logger.error(f"GitHub Parallel Fetch Error: {msg} — {e}")
            return path, f"[SYSTEM ERROR: {msg}]"

    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        tasks = [_fetch(client, p) for p in paths]
        results = await asyncio.gather(*tasks)

    # Format into standard codebase layout with truncation
    output = []
    total_chars = 0
    truncated = False

    for path, content in results:
        header = f"--- {path} ---\n"
        if total_chars + len(header) + len(content) > _cfg.max_codebase_chars:
            output.append(f"{header}[TRUNCATED: File omitted to stay within token limits]")
            truncated = True
            continue

        output.append(f"{header}{content}")
        total_chars += len(output[-1]) + 2  # +2 for \n\n

    if truncated:
        output.append("\n[!] WARNING: Output has been partially truncated to prevent token limit errors.")

    return "\n\n".join(output)


async def github_list_multiple_directories(
    owner: str,
    repo: str,
    paths: list[str],
    ref: str = "HEAD",
) -> dict:
    """List files and directories for multiple paths in parallel.

    Args:
        owner: The GitHub organisation or username.
        repo: The repository name.
        paths: List of directory paths.
        ref: The branch, tag, commit. Defaults to "HEAD".

    Returns:
        A dict mapping paths to their directory entries.
    """
    if not paths:
        return {"status": "ok", "results": {}}

    async def _list_one(client: httpx.AsyncClient, path: str):
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        try:
            resp = await client.get(url, params={"ref": ref}, timeout=15)
            resp.raise_for_status()
            items = resp.json()
            if not isinstance(items, list):
                return path, [{"name": items["name"], "type": "file", "path": items["path"]}]
            entries = [
                {
                    "name": i["name"],
                    "type": "dir" if i["type"] == "dir" else "file",
                    "path": i["path"],
                }
                for i in items
            ]
            return path, entries
        except Exception as e:
            msg = f"List error for '{os.path.basename(path) or 'root'}'"
            logger.error(f"GitHub Parallel List Error: {msg} — {e}")
            return path, [{"name": "error", "type": "error", "message": f"[SYSTEM ERROR: {msg}]"}]

    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        tasks = [_list_one(client, p) for p in paths]
        results = await asyncio.gather(*tasks)

    return {"status": "ok", "results": dict(results)}


async def github_get_recursive_tree(
    owner: str,
    repo: str,
    path: str = "",
    ref: str = "HEAD",
) -> dict:
    """Get a recursive list of all files in a repository or subdirectory.

    Uses the Git Trees API to fetch the entire file tree in one call.

    Args:
        owner: The GitHub organisation or username.
        repo: The repository name.
        path: Optional filter path (e.g. "src").
        ref: The branch, tag, or commit SHA. Defaults to "HEAD".

    Returns:
        A dict with "files" (list of paths) and "status".
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            resp = await client.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            tree = data.get("tree", [])
            # Filter for blobs (files) and path prefix
            path = path.strip("/")
            prefix = f"{path}/" if path else ""

            files = [item["path"] for item in tree if item["type"] == "blob" and item["path"].startswith(prefix)]

            return {
                "status": "ok",
                "files": files,
                "count": len(files),
                "truncated": bool(data.get("truncated", False)),
            }
        except httpx.HTTPStatusError as e:
            # Handle possible 404 ref resolution errors, e.g., if symbolic 'HEAD' is not supported on /git/trees/
            if ref == "HEAD" and e.response.status_code == 404:
                logger.warning("HEAD ref failed with 404, trying to resolve repository default branch...")
                # 1. Fetch repo metadata to find default branch
                repo_url = f"https://api.github.com/repos/{owner}/{repo}"
                try:
                    repo_resp = await client.get(repo_url, timeout=10)
                    if repo_resp.status_code == 200:
                        default_branch = repo_resp.json().get("default_branch")
                        if default_branch and default_branch != "HEAD":
                            logger.info(f"Resolved default branch to '{default_branch}', retrying tree fetch...")
                            retry_url = (
                                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
                            )
                            retry_resp = await client.get(retry_url, timeout=20)
                            if retry_resp.status_code == 200:
                                data = retry_resp.json()
                                tree = data.get("tree", [])
                                path = path.strip("/")
                                prefix = f"{path}/" if path else ""
                                files = [
                                    item["path"]
                                    for item in tree
                                    if item["type"] == "blob" and item["path"].startswith(prefix)
                                ]
                                return {
                                    "status": "ok",
                                    "files": files,
                                    "count": len(files),
                                    "truncated": bool(data.get("truncated", False)),
                                }
                except Exception as repo_err:
                    logger.debug(f"Failed to fetch repo default branch: {repo_err}")

                # 2. Hardcoded common default branches fallback
                for fallback_branch in ("main", "master"):
                    try:
                        logger.info(f"Attempting fallback to '{fallback_branch}' branch...")
                        retry_url = (
                            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{fallback_branch}?recursive=1"
                        )
                        retry_resp = await client.get(retry_url, timeout=20)
                        if retry_resp.status_code == 200:
                            data = retry_resp.json()
                            tree = data.get("tree", [])
                            path = path.strip("/")
                            prefix = f"{path}/" if path else ""
                            files = [
                                item["path"]
                                for item in tree
                                if item["type"] == "blob" and item["path"].startswith(prefix)
                            ]
                            return {
                                "status": "ok",
                                "files": files,
                                "count": len(files),
                                "truncated": bool(data.get("truncated", False)),
                            }
                    except Exception as fallback_err:
                        logger.debug(f"Fallback to {fallback_branch} failed: {fallback_err}")

            msg = f"HTTP {e.response.status_code} fetching tree"
            logger.error(f"GitHub Tree Error: {msg}")
            return {"status": "error", "files": [], "message": f"[SYSTEM ERROR: {msg}]"}
        except Exception as e:
            logger.error(f"GitHub Tree Error: {e}")
            return {
                "status": "error",
                "files": [],
                "message": "[SYSTEM ERROR: Failed to fetch repository tree]",
            }


async def _walk_repo_via_contents(owner: str, repo: str, ref: str = "HEAD") -> list[str]:
    """Recursively walk a repo via the Contents API to enumerate all blob paths.

    Fallback for when the Git Trees API truncates (repos with >100k entries):
    `?recursive=1` silently caps results, so we BFS the directory tree instead.
    Vendored/generated directories are pruned during the walk.
    """
    from pathlib import PurePosixPath
    from .file_tool import in_skipped_dir

    found: list[str] = []
    queue: list[str] = [""]
    visited: set[str] = set()

    while queue:
        batch, queue = queue[:30], queue[30:]
        res = await github_list_multiple_directories(owner, repo, batch, ref)
        for _dpath, entries in res.get("results", {}).items():
            for entry in entries:
                etype = entry.get("type")
                epath = entry.get("path", "")
                if not epath:
                    continue
                if etype == "dir":
                    if epath not in visited and not in_skipped_dir(PurePosixPath(epath).parts):
                        visited.add(epath)
                        queue.append(epath)
                elif etype == "file":
                    found.append(epath)
    return found


async def github_ingest_repository(
    owner: str,
    repo: str,
    ref: str = "HEAD",
) -> dict:
    """Deterministically ingest an ENTIRE GitHub repository in a single call.

    Walks the full file tree, excludes ONLY binary/media files and vendored
    directories (denylist — not a hand-picked allowlist), fetches every remaining
    file, and returns both a parser-compatible `codebase` string and a structured
    manifest of exactly what was and was not ingested. This replaces the previous
    LLM-driven "select core files, batch 30 at a time" flow, which silently missed
    files and whole folders.

    Args:
        owner: The GitHub organisation or username.
        repo: The repository name.
        ref: The branch, tag, or commit SHA. Defaults to "HEAD".

    Returns:
        A dict with: status, codebase (formatted "--- path ---" blocks), files,
        skipped (list of {path, reason}), total_files, fetched_files,
        truncated_tree, bytes.
    """
    from pathlib import PurePosixPath
    from ..config import Config
    from .file_tool import is_ingestible_file, in_skipped_dir

    _cfg = Config()
    budget = _cfg.max_repo_codebase_chars

    # 1. INVENTORY — full recursive tree, with truncation detection + fallback.
    tree = await github_get_recursive_tree(owner, repo, "", ref)
    if tree.get("status") != "ok":
        return {
            "status": "error",
            "codebase": tree.get("message", "[SYSTEM ERROR: failed to fetch repository tree]"),
            "files": [],
            "skipped": [],
            "total_files": 0,
            "fetched_files": 0,
            "truncated_tree": False,
            "bytes": 0,
        }

    all_paths = list(tree.get("files", []))
    truncated_tree = bool(tree.get("truncated"))
    if truncated_tree:
        logger.warning(
            "github_ingest_repository: Git tree was truncated; "
            "falling back to recursive Contents-API walk to recover missing paths."
        )
        walked = await _walk_repo_via_contents(owner, repo, ref)
        all_paths = sorted(set(all_paths) | set(walked))

    # 2. FILTER — denylist extensions + vendored/generated directories.
    eligible: list[str] = []
    skipped: list[dict] = []
    for p in all_paths:
        parts = PurePosixPath(p).parts
        if in_skipped_dir(parts):
            continue  # vendored/generated — excluded by design, not a "miss"
        if not is_ingestible_file(p):
            skipped.append({"path": p, "reason": "binary/media (denylisted extension)"})
            continue
        eligible.append(p)

    # 3. FETCH — every eligible blob, bounded concurrency.
    sem = asyncio.Semaphore(16)

    async def _fetch_one(client: httpx.AsyncClient, path: str):
        async with sem:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            try:
                resp = await client.get(url, params={"ref": ref}, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                if data.get("encoding") == "base64":
                    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                else:
                    content = data.get("content", "")
                if path.lower().endswith(".ipynb"):
                    content = _preprocess_ipynb(content)
                return path, content, None
            except httpx.HTTPStatusError as e:
                return path, None, f"HTTP {e.response.status_code} fetching file"
            except Exception as e:
                return path, None, f"fetch error: {e.__class__.__name__}"

    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        results = await asyncio.gather(*[_fetch_one(client, p) for p in eligible])

    # 4. ASSEMBLE — formatted codebase string; surface budget overflow, never drop silently.
    output: list[str] = []
    files: list[dict] = []
    total_chars = 0

    # Prioritize key files like pyproject.toml and README.md so they are processed before budget limit
    def is_priority(path_str: str) -> bool:
        name = os.path.basename(path_str).lower()
        return name in {
            "pyproject.toml",
            "requirements.txt",
            "readme.md",
            ".env.example",
            "package.json",
            "cargo.toml",
            "setup.py",
        }

    results_sorted = sorted(results, key=lambda x: not is_priority(x[0]))

    for path, content, err in results_sorted:
        if err:
            skipped.append({"path": path, "reason": err})
            continue
        block = f"--- {path} ---\n{content}"
        if total_chars + len(block) + 2 > budget:
            skipped.append({"path": path, "reason": "codebase ingest budget exceeded"})
            continue
        files.append({"path": path, "bytes": len(content)})
        output.append(block)
        total_chars += len(block) + 2

    codebase = "\n\n".join(output)
    if any(s["reason"] == "codebase ingest budget exceeded" for s in skipped):
        codebase += (
            "\n\n[!] WARNING: Repository exceeded the ingest budget; some files were "
            "omitted (see the skipped manifest for exact paths)."
        )

    logger.info(
        f"github_ingest_repository: {repo} — fetched {len(files)}/{len(eligible)} eligible files, "
        f"{len(skipped)} skipped, truncated_tree={truncated_tree}."
    )

    return {
        "status": "ok",
        "codebase": codebase,
        "files": files,
        "skipped": skipped,
        "total_files": len(eligible),
        "fetched_files": len(files),
        "truncated_tree": truncated_tree,
        "bytes": total_chars,
    }


# ---------------------------------------------------------------------------
# WRITE ACCESS TOOLS (REST Fallbacks for Remediation)
# ---------------------------------------------------------------------------


async def github_create_branch(
    owner: str,
    repo: str,
    branch: str,
    from_branch: str = "main",
) -> dict:
    """
    Creates a new branch in a GitHub repository from a source branch.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch: The name of the new branch to create.
        from_branch: The source branch to branch from.
    """
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            # 1. Get the SHA of the base branch. A 404 here is ambiguous (the repo
            # may not exist / be inaccessible, OR the base branch name may be wrong
            # — e.g. the repo defaults to 'master' but we asked for 'main'). Resolve
            # the ambiguity below instead of reporting every 404 as "branch failed".
            base_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{from_branch}"
            resp = await client.get(base_url, timeout=15)

            if resp.status_code == 404:
                # Probe the repo itself to tell "no repo / no access" from
                # "wrong base branch", and recover by using the real default branch.
                repo_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}", timeout=15)
                if repo_resp.status_code in (404, 401, 403):
                    return {
                        "status": "error",
                        "error": "REPO_NOT_FOUND_OR_NO_ACCESS",
                        "message": (
                            f"Repository '{owner}/{repo}' was not found or the GITHUB_TOKEN "
                            f"has no access to it (HTTP {repo_resp.status_code}). Verify the "
                            "owner/repo and that the token has 'repo'/'contents' scope for it."
                        ),
                    }
                repo_resp.raise_for_status()

                default_branch = str(repo_resp.json().get("default_branch") or "").strip()
                if default_branch and default_branch != from_branch:
                    logger.warning(
                        "github_create_branch: base '%s' not found in %s/%s; falling back to default branch '%s'.",
                        from_branch,
                        owner,
                        repo,
                        default_branch,
                    )
                    from_branch = default_branch
                    resp = await client.get(
                        f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
                        timeout=15,
                    )
                else:
                    return {
                        "status": "error",
                        "error": "BASE_BRANCH_NOT_FOUND",
                        "message": (
                            f"Base branch '{from_branch}' was not found in '{owner}/{repo}' "
                            f"(repo default is '{default_branch or 'unknown'}'). Set "
                            "GITHUB_BASE_BRANCH to the correct base branch."
                        ),
                    }

            resp.raise_for_status()
            base_sha = resp.json()["object"]["sha"]

            # 2. Create the new reference
            create_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
            payload = {"ref": f"refs/heads/{branch}", "sha": base_sha}
            resp = await client.post(create_url, json=payload, timeout=15)
            resp.raise_for_status()
            return {"status": "ok", "branch": branch, "base_branch": from_branch, "sha": base_sha}
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} creating branch '{branch}'"
            if e.response.status_code == 422:  # Already exists
                return {
                    "status": "ok",
                    "message": "Branch already exists",
                    "branch": branch,
                    "base_branch": from_branch,
                }
            logger.error(f"GitHub Branch Error: {msg}")
            return {"status": "error", "message": msg}
        except Exception as e:
            logger.error(f"GitHub Branch Error: {e}")
            return {"status": "error", "message": str(e)}


async def github_create_or_update_file(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
    sha: str = "",
) -> dict:
    """
    Creates or updates a file in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        path: Path to the file.
        content: Verbatim text content of the file.
        message: Commit message.
        branch: The branch to commit to.
        sha: The blob SHA of the file (required for updates).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Base64 encode the content
    b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": message,
        "content": b64_content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            resp = await client.put(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {"status": "ok", "path": path, "commit_sha": data["commit"]["sha"]}
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} updating '{path}'"
            logger.error(f"GitHub File Error: {msg} — {e.response.text}")
            return {"status": "error", "message": msg}
        except Exception as e:
            logger.error(f"GitHub File Error: {e}")
            return {"status": "error", "message": str(e)}


async def github_create_pull_request(
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> dict:
    """
    Creates a new pull request in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: PR title.
        body: PR description (Markdown).
        head: The name of the branch where your changes are implemented.
        base: The name of the branch you want your changes pulled into.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            resp = await client.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "pr_url": data["html_url"],
                "number": data["number"],
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 422:
                logger.info(f"422 error creating PR. Checking for existing PR for head={head}")
                search_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
                for head_query in [f"{owner}:{head}", head]:
                    try:
                        search_resp = await client.get(
                            search_url,
                            params={"head": head_query, "base": base, "state": "open"},
                            timeout=15,
                        )
                        if search_resp.status_code == 200:
                            pulls = search_resp.json()
                            if pulls and isinstance(pulls, list):
                                pr_data = pulls[0]
                                return {
                                    "status": "ok",
                                    "pr_url": pr_data["html_url"],
                                    "number": pr_data["number"],
                                    "message": "Pull request already exists",
                                }
                    except Exception as se:
                        logger.error(f"Failed to query existing PR with head_query={head_query}: {se}")

                try:
                    search_resp = await client.get(search_url, params={"state": "open"}, timeout=15)
                    if search_resp.status_code == 200:
                        pulls = search_resp.json()
                        if isinstance(pulls, list):
                            for pr_data in pulls:
                                if pr_data.get("head", {}).get("ref") == head:
                                    return {
                                        "status": "ok",
                                        "pr_url": pr_data["html_url"],
                                        "number": pr_data["number"],
                                        "message": "Pull request already exists",
                                    }
                except Exception as se:
                    logger.error(f"Failed to list all open PRs as fallback: {se}")

            msg = f"HTTP {e.response.status_code} creating PR"
            logger.error(f"GitHub PR Error: {msg} — {e.response.text}")
            return {"status": "error", "message": msg}
        except Exception as e:
            logger.error(f"GitHub PR Error: {e}")
            return {"status": "error", "message": str(e)}


async def github_delete_file(
    owner: str,
    repo: str,
    path: str,
    message: str,
    branch: str,
    sha: str,
) -> dict:
    """Delete a file from a GitHub repository on a given branch.

    Args:
        owner: Repository owner.
        repo: Repository name.
        path: Path to the file to delete.
        message: Commit message.
        branch: The branch to commit the deletion to.
        sha: The blob SHA of the file being deleted (required by the API).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    payload = {"message": message, "branch": branch, "sha": sha}
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        try:
            resp = await client.request("DELETE", url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {"status": "ok", "path": path, "commit_sha": data.get("commit", {}).get("sha", "")}
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} deleting '{path}'"
            logger.error(f"GitHub Delete Error: {msg} — {e.response.text}")
            return {"status": "error", "message": msg}
        except Exception as e:
            logger.error(f"GitHub Delete Error: {e}")
            return {"status": "error", "message": str(e)}


async def _github_fetch_raw(client: httpx.AsyncClient, owner: str, repo: str, path: str, ref: str) -> dict:
    """Fetch a file's EXACT decoded content + blob sha (no .ipynb preprocessing).

    Used by the deterministic remediation apply step: we must merge against the
    verbatim file content so an exact-snippet match is reliable.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    resp = await client.get(url, params={"ref": ref}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") == "base64":
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    else:
        content = data.get("content", "")
    return {"content": content, "sha": data.get("sha", "")}


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _merge_modify(current: str, original_snippet: str | None, replacement_snippet: str | None):
    """Deterministically apply a single 'modify' change with exact-match verification.

    Returns (merged_content, None) on success, or (None, reason) when the snippet
    is missing, absent, or ambiguous — so the caller can FAIL LOUD rather than
    silently corrupting the file.
    """
    orig = _normalize_newlines(original_snippet)
    if not orig.strip():
        return None, "original_snippet missing/empty for change_type='modify'"
    norm = _normalize_newlines(current)
    count = norm.count(orig)
    if count == 0:
        return None, "original_snippet not found in current file content"
    if count > 1:
        return None, f"original_snippet is ambiguous ({count} matches) — refusing to guess"
    merged = norm.replace(orig, _normalize_newlines(replacement_snippet), 1)
    return merged, None


async def github_apply_remediation_plan(
    plan: dict | None = None,
    owner: str = "",
    repo: str = "",
    base_branch: str = "",
    pr_branch: str = "",
    tool_context=None,
) -> dict:
    """Deterministically apply a RemediationPlan and open a PR — no LLM merging.

    Creates the PR branch, then applies each CodeChange in Python: for 'modify'
    it fetches the current file and replaces the EXACT original_snippet (failing
    loud on a missing/ambiguous match instead of mangling the file); 'create'
    writes the replacement content; 'delete' removes the file. A PR is opened only
    if at least one change committed. Reads the plan from session state when not
    passed explicitly, so the executor can call it with no arguments.

    Returns:
        {status: ok|partial|error, pr_url, pr_number, committed:[...],
         failed:[{finding_id, file_path, reason}], branch, message}.
    """
    # Resolve the plan from state if not passed (LLM calls this with no args).
    if plan is None and tool_context is not None:
        raw = (getattr(tool_context, "state", {}) or {}).get("remediation_plan", "")
        if isinstance(raw, str) and raw.strip():
            try:
                plan = json.loads(raw)
            except Exception:
                plan = None
        elif isinstance(raw, dict):
            plan = raw

    # Check if this is a Bitbucket repository
    is_bitbucket = False
    if tool_context is not None:
        state = getattr(tool_context, "state", {}) or {}
        user_request = state.get("user_request", "")
        prev_user_request = state.get("_previous_user_request", "")
        if "bitbucket.org" in str(user_request).lower() or "bitbucket.org" in str(prev_user_request).lower():
            is_bitbucket = True

    if not is_bitbucket and plan is not None:
        if "bitbucket.org" in str(plan.get("target_repo", "")).lower():
            is_bitbucket = True

    if is_bitbucket:
        from .bitbucket_tool import bitbucket_apply_remediation_plan

        return await bitbucket_apply_remediation_plan(
            plan=plan,
            base_branch=base_branch,
            pr_branch=pr_branch,
            tool_context=tool_context,
        )
    if not isinstance(plan, dict):
        return {"status": "error", "message": "No usable remediation plan available.", "committed": [], "failed": []}

    target = str(plan.get("target_repo") or "").strip()
    if (not owner or not repo) and "/" in target:
        t_owner, _, t_repo = target.partition("/")
        owner = owner or t_owner.strip()
        repo = repo or t_repo.strip()
    base_branch = base_branch or str(plan.get("base_branch") or "main")
    pr_branch = pr_branch or str(plan.get("pr_branch") or "agent_guardian/review")

    if not owner or not repo:
        return {"status": "error", "message": "Could not resolve owner/repo from plan.", "committed": [], "failed": []}

    changes = plan.get("changes", []) or []

    # 1. Create the PR branch (idempotent on 422 / already-exists).
    br = await github_create_branch(owner, repo, pr_branch, base_branch)
    if br.get("status") != "ok":
        return {
            "status": "error",
            "message": f"Branch creation failed: {br.get('message')}",
            "committed": [],
            "failed": [],
        }
    # github_create_branch may have fallen back to the repo's real default branch
    # (e.g. 'master' when we asked for 'main'); open the PR against that same base.
    base_branch = str(br.get("base_branch") or base_branch)

    committed: list[dict] = []
    failed: list[dict] = []

    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
        for ch in changes:
            fid = ch.get("finding_id", "?")
            fpath = ch.get("file_path", "")
            ctype = (ch.get("change_type") or "modify").lower()
            commit_id = str((getattr(tool_context, "state", {}) or {}).get("remediation_commit_id", "")).strip()
            prefix = f"{commit_id}: " if commit_id and commit_id.lower() not in ("none", "null") else ""
            commit_msg = f"{prefix}[Guardian] {fid}: {ch.get('rationale', 'automated remediation')}"

            if not fpath:
                failed.append({"finding_id": fid, "file_path": fpath, "reason": "missing file_path"})
                continue

            try:
                if ctype == "create":
                    content = ch.get("replacement_snippet") or ""
                    # Upsert: if the file already exists on the branch, GitHub
                    # requires its blob sha — a bare create returns 422.
                    try:
                        existing = await _github_fetch_raw(client, owner, repo, fpath, pr_branch)
                        existing_sha = existing.get("sha", "")
                    except Exception:
                        existing_sha = ""
                    res = await github_create_or_update_file(
                        owner, repo, fpath, content, commit_msg, pr_branch, existing_sha
                    )
                elif ctype == "delete":
                    try:
                        cur = await _github_fetch_raw(client, owner, repo, fpath, pr_branch)
                    except Exception:
                        failed.append({"finding_id": fid, "file_path": fpath, "reason": "file not found for delete"})
                        continue
                    res = await github_delete_file(owner, repo, fpath, commit_msg, pr_branch, cur.get("sha", ""))
                else:  # modify
                    try:
                        cur = await _github_fetch_raw(client, owner, repo, fpath, pr_branch)
                    except Exception as fe:
                        failed.append(
                            {
                                "finding_id": fid,
                                "file_path": fpath,
                                "reason": f"could not fetch file: {fe.__class__.__name__}",
                            }
                        )
                        continue
                    merged, err = _merge_modify(
                        cur.get("content", ""), ch.get("original_snippet"), ch.get("replacement_snippet")
                    )
                    if err:
                        failed.append({"finding_id": fid, "file_path": fpath, "reason": err})
                        continue
                    res = await github_create_or_update_file(
                        owner, repo, fpath, merged, commit_msg, pr_branch, cur.get("sha", "")
                    )

                if res.get("status") == "ok":
                    committed.append({"finding_id": fid, "file_path": fpath, "change_type": ctype})
                else:
                    failed.append(
                        {"finding_id": fid, "file_path": fpath, "reason": res.get("message", "commit failed")}
                    )
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

    # 3. Open the PR (idempotent — returns existing PR URL on 422).
    pr = await github_create_pull_request(
        owner,
        repo,
        plan.get("pr_title") or "[Agent Guardian] Automated remediation",
        plan.get("pr_body") or "Automated remediation by Agent Guardian.",
        pr_branch,
        base_branch,
    )
    if pr.get("status") != "ok":
        return {
            "status": "error",
            "message": f"Changes committed but PR creation failed: {pr.get('message')}",
            "committed": committed,
            "failed": failed,
            "pr_url": "",
            "branch": pr_branch,
        }

    return {
        "status": "partial" if failed else "ok",
        "pr_url": pr.get("pr_url", ""),
        "pr_number": pr.get("number"),
        "committed": committed,
        "failed": failed,
        "branch": pr_branch,
    }


# ---------------------------------------------------------------------------
# PREFIX-LESS ALIASES FOR COMPATIBILITY
# ---------------------------------------------------------------------------


async def create_branch(
    owner: str,
    repo: str,
    branch: str,
    from_branch: str = "main",
) -> dict:
    """Creates a new branch in a GitHub repository from a source branch."""
    return await github_create_branch(owner, repo, branch, from_branch)


async def create_or_update_file(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
    sha: str = "",
) -> dict:
    """Creates or updates a file in a GitHub repository."""
    return await github_create_or_update_file(owner, repo, path, content, message, branch, sha)


async def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> dict:
    """Creates a new pull request in a GitHub repository."""
    return await github_create_pull_request(owner, repo, title, body, head, base)


async def get_file_contents(
    owner: str,
    repo: str,
    path: str,
    ref: str = "HEAD",
) -> dict:
    """Fetch the contents of a single file from a GitHub repository (Async)."""
    return await github_get_file_contents(owner, repo, path, ref)


async def github_fetch_file_raw(owner: str, repo: str, path: str, ref: str = "main") -> dict:
    """Public verbatim fetch — the EXACT decoded file content (no .ipynb
    preprocessing), identical to what the remediation apply step matches against.

    Lets the planner be fed the real source so its `original_snippet`s are copied
    character-for-character and survive `_merge_modify`'s exact-match check.

    Returns {status: ok|error, content, sha, message}.
    """
    try:
        async with httpx.AsyncClient(headers=_headers(), follow_redirects=True) as client:
            data = await _github_fetch_raw(client, owner, repo, path, ref)
        return {"status": "ok", "content": data.get("content", ""), "sha": data.get("sha", "")}
    except Exception as e:
        return {"status": "error", "message": str(e), "content": "", "sha": ""}
