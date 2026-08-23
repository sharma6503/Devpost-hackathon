from __future__ import annotations
import pytest
import base64
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from agent_guardian.tools.github_tool import (
    github_create_branch,
    github_create_or_update_file,
    github_create_pull_request,
    github_get_recursive_tree,
)


@pytest.mark.asyncio
async def test_github_create_branch_success():
    with (
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = {"object": {"sha": "base_sha_123"}}

        mock_post.return_value = MagicMock(status_code=201)

        result = await github_create_branch("owner", "repo", "new-branch", "main")

        assert result["status"] == "ok"
        assert result["branch"] == "new-branch"
        assert mock_post.called


@pytest.mark.asyncio
async def test_github_create_or_update_file_success():
    with patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put:
        mock_put.return_value = MagicMock(status_code=200)
        mock_put.return_value.json.return_value = {"commit": {"sha": "commit_sha_456"}}

        content = "hello world"
        expected_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        result = await github_create_or_update_file(
            "owner",
            "repo",
            "path/to/file.py",
            content,
            "feat: fix",
            "branch-1",
            "file_sha_abc",
        )

        assert result["status"] == "ok"
        assert result["commit_sha"] == "commit_sha_456"

        args, kwargs = mock_put.call_args
        payload = kwargs["json"]
        assert payload["content"] == expected_b64


@pytest.mark.asyncio
async def test_github_create_pull_request_success():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.json.return_value = {
            "html_url": "https://github.com/pr/1",
            "number": 1,
        }

        result = await github_create_pull_request("owner", "repo", "Title", "Body", "head-branch", "main")

        assert result["status"] == "ok"
        assert result["pr_url"] == "https://github.com/pr/1"


@pytest.mark.asyncio
async def test_github_create_pull_request_already_exists_422():
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        # 1. Post returns 422 HTTPStatusError
        mock_response = MagicMock(status_code=422)
        mock_response.text = "A pull request already exists for..."
        mock_post.side_effect = httpx.HTTPStatusError(
            message="Unprocessable Entity", request=MagicMock(), response=mock_response
        )

        # 2. First GET for head parameter returns the matching PR
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = [{"html_url": "https://github.com/pr/already-exists", "number": 42}]
        mock_get.return_value = mock_get_response

        result = await github_create_pull_request("owner", "repo", "Title", "Body", "head-branch", "main")

        assert result["status"] == "ok"
        assert result["pr_url"] == "https://github.com/pr/already-exists"
        assert result["number"] == 42
        assert "already exists" in result["message"]


@pytest.mark.asyncio
async def test_github_create_pull_request_already_exists_fallback():
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        # 1. Post returns 422
        mock_response = MagicMock(status_code=422)
        mock_response.text = "A pull request already exists for..."
        mock_post.side_effect = httpx.HTTPStatusError(
            message="Unprocessable Entity", request=MagicMock(), response=mock_response
        )

        # 2. First GETs with head query return empty list []
        # 3. Third GET (list-all open pulls) returns a list with the matching head ref
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: []),  # owner:head
            MagicMock(status_code=200, json=lambda: []),  # head
            MagicMock(
                status_code=200,
                json=lambda: [  # fallback list-all
                    {
                        "html_url": "https://github.com/pr/fallback-match",
                        "number": 99,
                        "head": {"ref": "head-branch"},
                    }
                ],
            ),
        ]

        result = await github_create_pull_request("owner", "repo", "Title", "Body", "head-branch", "main")

        assert result["status"] == "ok"
        assert result["pr_url"] == "https://github.com/pr/fallback-match"
        assert result["number"] == 99


@pytest.mark.asyncio
async def test_github_get_recursive_tree_success():
    """Verify that github_get_recursive_tree successfully retrieves the tree when the ref works directly."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "tree": [
                {"path": "src/main.py", "type": "blob"},
                {"path": "README.md", "type": "blob"},
                {"path": "tests", "type": "tree"},
            ]
        }
        mock_get.return_value = mock_resp

        result = await github_get_recursive_tree("owner", "repo", "src", "HEAD")

        assert result["status"] == "ok"
        assert result["files"] == ["src/main.py"]
        assert result["count"] == 1
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/git/trees/HEAD?recursive=1",
            timeout=20,
        )


@pytest.mark.asyncio
async def test_github_get_recursive_tree_head_fallback_to_default_branch():
    """Verify that if HEAD fails with 404, we fetch default branch name and retry successfully."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # Mock 1st call (HEAD tree): 404
        mock_404_resp = MagicMock(status_code=404)
        mock_404_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Not Found", request=MagicMock(), response=mock_404_resp
        )

        # Mock 2nd call (repo metadata): 200 with default_branch="develop"
        mock_repo_resp = MagicMock(status_code=200)
        mock_repo_resp.json.return_value = {"default_branch": "develop"}

        # Mock 3rd call (develop tree): 200
        mock_tree_resp = MagicMock(status_code=200)
        mock_tree_resp.json.return_value = {"tree": [{"path": "develop_file.py", "type": "blob"}]}

        mock_get.side_effect = [mock_404_resp, mock_repo_resp, mock_tree_resp]

        result = await github_get_recursive_tree("owner", "repo", "", "HEAD")

        assert result["status"] == "ok"
        assert result["files"] == ["develop_file.py"]
        assert result["count"] == 1
        assert mock_get.call_count == 3


@pytest.mark.asyncio
async def test_github_get_recursive_tree_head_fallback_to_common_branches():
    """Verify that if HEAD and metadata both fail, we fallback to 'main' or 'master' branch tree."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # Mock 1st call (HEAD tree): 404
        mock_404_resp = MagicMock(status_code=404)
        mock_404_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Not Found", request=MagicMock(), response=mock_404_resp
        )

        # Mock 2nd call (repo metadata): 500 error or some exception
        mock_repo_500 = MagicMock(status_code=500)

        # Mock 3rd call (main tree): 404
        mock_main_404 = MagicMock(status_code=404)

        # Mock 4th call (master tree): 200
        mock_master_200 = MagicMock(status_code=200)
        mock_master_200.json.return_value = {"tree": [{"path": "master_file.py", "type": "blob"}]}

        mock_get.side_effect = [mock_404_resp, mock_repo_500, mock_main_404, mock_master_200]

        result = await github_get_recursive_tree("owner", "repo", "", "HEAD")

        assert result["status"] == "ok"
        assert result["files"] == ["master_file.py"]
        assert result["count"] == 1
        assert mock_get.call_count == 4
