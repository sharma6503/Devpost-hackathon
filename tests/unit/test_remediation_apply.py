from __future__ import annotations
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent_guardian.tools.github_tool import (
    _merge_modify,
    _validate_syntax,
    github_apply_remediation_plan,
)


# ---------------------------------------------------------------------------
# _merge_modify — the exact-match verification at the heart of safe apply
# ---------------------------------------------------------------------------
def test_merge_modify_clean_replace():
    current = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    merged, err = _merge_modify(current, "    return 1", "    return 11")
    assert err is None
    assert "return 11" in merged
    assert "return 2" in merged  # rest of file preserved


def test_merge_modify_snippet_not_found():
    merged, err = _merge_modify("x = 1\n", "y = 2", "y = 3")
    assert merged is None
    assert "not found" in err


def test_merge_modify_ambiguous():
    current = "v = 0\nv = 0\n"
    merged, err = _merge_modify(current, "v = 0", "v = 9")
    assert merged is None
    assert "ambiguous" in err


def test_merge_modify_missing_original():
    merged, err = _merge_modify("x = 1", None, "x = 2")
    assert merged is None
    assert "missing" in err


def test_merge_modify_crlf_normalized():
    # File has CRLF line endings; snippet uses LF. Must still match.
    current = "line1\r\nline2\r\nline3\r\n"
    merged, err = _merge_modify(current, "line2\n", "LINE2\n")
    assert err is None
    assert "LINE2" in merged


def test_merge_modify_resilient_whitespace():
    # File has trailing whitespace on lines, snippet has clean whitespace
    current = "def add(a, b):   \n    return a + b  \n"
    snippet = "def add(a, b):\n    return a + b"
    replacement = "def add(a: int, b: int) -> int:\n    return a + b"
    merged, err = _merge_modify(current, snippet, replacement)
    assert err is None
    assert "def add(a: int, b: int) -> int:" in merged


def test_validate_syntax():
    valid_py = "x = 1\ndef foo(): pass\n"
    invalid_py = "def foo(:\n"
    is_valid, err = _validate_syntax("test.py", valid_py)
    assert is_valid is True
    assert err is None

    is_valid, err = _validate_syntax("test.py", invalid_py)
    assert is_valid is False
    assert "Python SyntaxError" in err

    valid_json = '{"name": "agent"}'
    invalid_json = '{"name": "agent"'
    assert _validate_syntax("config.json", valid_json)[0] is True
    assert _validate_syntax("config.json", invalid_json)[0] is False


# ---------------------------------------------------------------------------
# github_apply_remediation_plan — orchestration with mocked GitHub helpers
# ---------------------------------------------------------------------------
_GH = "agent_guardian.tools.github_tool"


@pytest.mark.asyncio
async def test_apply_plan_mixed_changes():
    plan = {
        "target_repo": "acme/widget",
        "base_branch": "main",
        "pr_branch": "agent_guardian/review",
        "pr_title": "fix",
        "pr_body": "body",
        "changes": [
            {
                "finding_id": "A1",
                "file_path": "a.py",
                "change_type": "modify",
                "original_snippet": "old = 1",
                "replacement_snippet": "old = 2",
            },
            {
                "finding_id": "B1",
                "file_path": "b.py",
                "change_type": "modify",
                "original_snippet": "NOPE",
                "replacement_snippet": "x",
            },  # not found -> failed
            {"finding_id": "C1", "file_path": "c.py", "change_type": "create", "replacement_snippet": "print('new')"},
        ],
    }

    async def fake_fetch(client, owner, repo, path, ref):
        return {"content": "old = 1\n", "sha": "sha-" + path}

    with (
        patch(
            f"{_GH}.github_create_branch",
            new=AsyncMock(return_value={"status": "ok", "branch": "agent_guardian/review"}),
        ),
        patch(f"{_GH}._github_fetch_raw", new=AsyncMock(side_effect=fake_fetch)),
        patch(f"{_GH}.github_create_or_update_file", new=AsyncMock(return_value={"status": "ok", "commit_sha": "c"})),
        patch(
            f"{_GH}.github_create_pull_request",
            new=AsyncMock(
                return_value={"status": "ok", "pr_url": "https://github.com/acme/widget/pull/7", "number": 7}
            ),
        ),
    ):
        res = await github_apply_remediation_plan(plan=plan)

    assert res["status"] == "partial"  # one change failed
    assert res["pr_url"].endswith("/pull/7")
    committed_ids = {c["finding_id"] for c in res["committed"]}
    failed_ids = {f["finding_id"] for f in res["failed"]}
    assert committed_ids == {"A1", "C1"}
    assert failed_ids == {"B1"}


@pytest.mark.asyncio
async def test_apply_plan_no_changes_applied_skips_pr():
    plan = {
        "target_repo": "acme/widget",
        "pr_branch": "agent_guardian/review",
        "changes": [
            {
                "finding_id": "A1",
                "file_path": "a.py",
                "change_type": "modify",
                "original_snippet": "NOPE",
                "replacement_snippet": "x",
            },
        ],
    }
    pr_mock = AsyncMock(return_value={"status": "ok", "pr_url": "should-not-be-called"})
    with (
        patch(f"{_GH}.github_create_branch", new=AsyncMock(return_value={"status": "ok"})),
        patch(f"{_GH}._github_fetch_raw", new=AsyncMock(return_value={"content": "real = 1", "sha": "s"})),
        patch(f"{_GH}.github_create_or_update_file", new=AsyncMock(return_value={"status": "ok"})),
        patch(f"{_GH}.github_create_pull_request", new=pr_mock),
    ):
        res = await github_apply_remediation_plan(plan=plan)

    assert res["status"] == "error"
    assert res["pr_url"] == ""
    assert len(res["failed"]) == 1
    pr_mock.assert_not_called()  # no PR opened when nothing committed


@pytest.mark.asyncio
async def test_apply_plan_resolves_owner_repo_from_target():
    plan = {"target_repo": "octo/cat", "pr_branch": "b", "changes": []}
    branch_mock = AsyncMock(return_value={"status": "ok"})
    with patch(f"{_GH}.github_create_branch", new=branch_mock):
        res = await github_apply_remediation_plan(plan=plan)
    # No changes -> error (nothing committed), but owner/repo must have resolved
    branch_mock.assert_awaited_once()
    args = branch_mock.await_args.args
    assert args[0] == "octo" and args[1] == "cat"
    assert res["status"] == "error"


@pytest.mark.asyncio
async def test_apply_plan_bitbucket():
    import json

    plan = {
        "target_repo": "imonline/agenticai.agentguardian",
        "pr_branch": "agent_guardian/review",
        "changes": [
            {
                "finding_id": "A1",
                "file_path": "a.py",
                "change_type": "create",
                "replacement_snippet": "CONTENT = 'new content'\n",
            },
        ],
    }
    mock_tc = MagicMock()
    mock_tc.state = {
        "remediation_plan": json.dumps(plan),
        "user_request": "https://bitbucket.org/imonline/agenticai.agentguardian/src/main",
    }

    _BB = "agent_guardian.tools.bitbucket_tool"
    with (
        patch(f"{_BB}.bitbucket_create_branch", new=AsyncMock(return_value={"status": "ok", "base_branch": "main"})),
        patch(f"{_BB}.bitbucket_commit_files", new=AsyncMock(return_value={"status": "ok"})),
        patch(
            f"{_BB}.bitbucket_create_pull_request",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "pr_url": "https://bitbucket.org/imonline/agenticai.agentguardian/pull-requests/1",
                    "number": 1,
                }
            ),
        ),
    ):
        res = await github_apply_remediation_plan(plan=plan, tool_context=mock_tc)

    assert res["status"] == "ok"
    assert res["pr_url"] == "https://bitbucket.org/imonline/agenticai.agentguardian/pull-requests/1"
    assert len(res["committed"]) == 1
    assert res["committed"][0]["finding_id"] == "A1"


@pytest.mark.asyncio
async def test_apply_plan_bitbucket_on_approve():
    plan = {
        "target_repo": "imonline/agenticai.agentguardian",
        "pr_branch": "agent_guardian/review",
        "changes": [
            {
                "finding_id": "A1",
                "file_path": "a.py",
                "change_type": "create",
                "replacement_snippet": "CONTENT = 'new content'\n",
            },
        ],
    }
    mock_tc = MagicMock()
    mock_tc.state = {
        "remediation_plan": json.dumps(plan),
        "user_request": "__AG_APPROVE_REMEDIATION__",
        "_previous_user_request": "https://bitbucket.org/imonline/agenticai.agentguardian/src/main",
    }

    _BB = "agent_guardian.tools.bitbucket_tool"
    with (
        patch(f"{_BB}.bitbucket_create_branch", new=AsyncMock(return_value={"status": "ok", "base_branch": "main"})),
        patch(f"{_BB}.bitbucket_commit_files", new=AsyncMock(return_value={"status": "ok"})),
        patch(
            f"{_BB}.bitbucket_create_pull_request",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "pr_url": "https://bitbucket.org/imonline/agenticai.agentguardian/pull-requests/1",
                    "number": 1,
                }
            ),
        ),
    ):
        res = await github_apply_remediation_plan(plan=None, tool_context=mock_tc)

    assert res["status"] == "ok"
    assert res["pr_url"] == "https://bitbucket.org/imonline/agenticai.agentguardian/pull-requests/1"
    assert len(res["committed"]) == 1
    assert res["committed"][0]["finding_id"] == "A1"


@pytest.mark.asyncio
async def test_apply_plan_syntax_error_rejected():
    plan = {
        "target_repo": "acme/widget",
        "base_branch": "main",
        "pr_branch": "agent_guardian/review",
        "pr_title": "fix syntax",
        "pr_body": "fix syntax body",
        "changes": [
            {
                "finding_id": "F-BAD-SYNTAX",
                "file_path": "src/bad.py",
                "change_type": "create",
                "replacement_snippet": "def broken(:\n",
            },
        ],
    }
    with (
        patch(f"{_GH}.github_create_branch", new=AsyncMock(return_value={"status": "ok"})),
        patch(f"{_GH}.github_create_or_update_file", new=AsyncMock(return_value={"status": "ok"})),
        patch(f"{_GH}.github_create_pull_request", new=AsyncMock(return_value={"status": "ok", "pr_url": "http://pr", "number": 1})),
    ):
        res = await github_apply_remediation_plan(plan=plan)

    assert res["status"] == "error"
    assert len(res["failed"]) == 1
    assert "Python SyntaxError" in res["failed"][0]["reason"]


@pytest.mark.asyncio
async def test_bitbucket_multiple_modifications_same_file():
    from agent_guardian.tools.bitbucket_tool import bitbucket_apply_remediation_plan

    plan = {
        "target_repo": "imonline/agenticai.agentguardian",
        "base_branch": "main",
        "pr_branch": "agent_guardian/review",
        "changes": [
            {
                "finding_id": "F1",
                "file_path": "server.py",
                "change_type": "modify",
                "original_snippet": "PORT = 80\n",
                "replacement_snippet": "PORT = 8080\n",
            },
            {
                "finding_id": "F2",
                "file_path": "server.py",
                "change_type": "modify",
                "original_snippet": "DEBUG = True\n",
                "replacement_snippet": "DEBUG = False\n",
            },
        ],
    }

    initial_server_py = "PORT = 80\nDEBUG = True\n"

    captured_additions = {}

    async def mock_commit(ws, repo, branch, msg, additions, deletions):
        nonlocal captured_additions
        captured_additions = additions
        return {"status": "ok"}

    _BB = "agent_guardian.tools.bitbucket_tool"
    with (
        patch(f"{_BB}.bitbucket_create_branch", new=AsyncMock(return_value={"status": "ok", "base_branch": "main"})),
        patch(f"{_BB}.bitbucket_commit_files", side_effect=mock_commit),
        patch(f"{_BB}.bitbucket_create_pull_request", new=AsyncMock(return_value={"status": "ok", "pr_url": "http://pr/1", "number": 1})),
        patch(f"{_BB}._make_client") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.text = initial_server_py
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        res = await bitbucket_apply_remediation_plan(plan=plan)

    assert res["status"] == "ok"
    assert len(res["committed"]) == 2
    assert "server.py" in captured_additions
    final_content = captured_additions["server.py"]
    assert "PORT = 8080\n" in final_content
    assert "DEBUG = False\n" in final_content
