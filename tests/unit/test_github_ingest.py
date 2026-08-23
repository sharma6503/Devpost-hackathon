from __future__ import annotations
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent_guardian.tools.github_tool import github_ingest_repository

_GH = "agent_guardian.tools.github_tool"


def _b64_resp(text: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
    return resp


@pytest.mark.asyncio
async def test_ingest_denylist_and_dirs():
    tree = {
        "status": "ok",
        "truncated": False,
        "files": ["main.py", "logo.png", "node_modules/dep.js", "go.mod"],
    }
    with (
        patch(f"{_GH}.github_get_recursive_tree", new=AsyncMock(return_value=tree)),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_b64_resp("content"))),
    ):
        res = await github_ingest_repository("o", "r")

    assert res["status"] == "ok"
    fetched = {f["path"] for f in res["files"]}
    # go.mod is captured (allowlist would have dropped it); main.py captured.
    assert fetched == {"main.py", "go.mod"}
    # node_modules excluded entirely (not even in skipped manifest).
    assert all("node_modules" not in s["path"] for s in res["skipped"])
    # binary png surfaced in the skipped manifest, not silently lost.
    assert any(s["path"] == "logo.png" for s in res["skipped"])
    assert res["truncated_tree"] is False


@pytest.mark.asyncio
async def test_ingest_truncated_tree_triggers_walk():
    tree = {"status": "ok", "truncated": True, "files": ["a.py"]}
    with (
        patch(f"{_GH}.github_get_recursive_tree", new=AsyncMock(return_value=tree)),
        patch(f"{_GH}._walk_repo_via_contents", new=AsyncMock(return_value=["a.py", "deep/b.py"])),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_b64_resp("x"))),
    ):
        res = await github_ingest_repository("o", "r")

    assert res["truncated_tree"] is True
    fetched = {f["path"] for f in res["files"]}
    # walk recovered the path the truncated tree missed.
    assert fetched == {"a.py", "deep/b.py"}


@pytest.mark.asyncio
async def test_ingest_tree_error_propagates():
    with patch(f"{_GH}.github_get_recursive_tree", new=AsyncMock(return_value={"status": "error", "message": "boom"})):
        res = await github_ingest_repository("o", "r")
    assert res["status"] == "error"
    assert res["fetched_files"] == 0
