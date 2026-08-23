from __future__ import annotations

import base64
import os
from unittest.mock import patch

import httpx

from agent_guardian.tools.bitbucket_tool import _make_client


def _get_expected_auth_header(user: str, pass_: str) -> str:
    encoded = base64.b64encode(f"{user}:{pass_}".encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def test_make_client_with_atatt_token_and_atlassian_username():
    """Verify Scoped API Tokens starting with ATATT use Basic Auth with ATLASSIAN_USERNAME."""
    custom_env = {
        "BITBUCKET_TOKEN": "ATATT3xFfG_mock_token_12345",
        "ATLASSIAN_USERNAME": "test_atlassian@example.com",
        "BITBUCKET_USERNAME": "",
        "BITBUCKET_APP_PASSWORD": "",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        client = _make_client()
        assert isinstance(client, httpx.AsyncClient)
        assert isinstance(client.auth, httpx.BasicAuth)
        assert client.auth._auth_header == _get_expected_auth_header(
            "test_atlassian@example.com", "ATATT3xFfG_mock_token_12345"
        )


def test_make_client_with_atatt_token_and_bitbucket_username():
    """Verify Scoped API Tokens use BITBUCKET_USERNAME if ATLASSIAN_USERNAME is unset."""
    custom_env = {
        "BITBUCKET_TOKEN": "ATATT3xFfG_mock_token_12345",
        "ATLASSIAN_USERNAME": "",
        "BITBUCKET_USERNAME": "test_bitbucket@example.com",
        "BITBUCKET_APP_PASSWORD": "",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        client = _make_client()
        assert isinstance(client, httpx.AsyncClient)
        assert isinstance(client.auth, httpx.BasicAuth)
        assert client.auth._auth_header == _get_expected_auth_header(
            "test_bitbucket@example.com", "ATATT3xFfG_mock_token_12345"
        )


def test_make_client_with_atatt_token_default_fallback():
    """Verify Scoped API Tokens fallback to empty username if both usernames are unset."""
    custom_env = {
        "BITBUCKET_TOKEN": "ATATT3xFfG_mock_token_12345",
        "ATLASSIAN_USERNAME": "",
        "BITBUCKET_USERNAME": "",
        "BITBUCKET_APP_PASSWORD": "",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        client = _make_client()
        assert isinstance(client, httpx.AsyncClient)
        assert isinstance(client.auth, httpx.BasicAuth)
        assert client.auth._auth_header == _get_expected_auth_header(
            "", "ATATT3xFfG_mock_token_12345"
        )


def test_make_client_with_bearer_token():
    """Verify regular Bitbucket tokens (non-ATATT) use the Bearer header."""
    custom_env = {
        "BITBUCKET_TOKEN": "regular_oauth_token_67890",
        "ATLASSIAN_USERNAME": "",
        "BITBUCKET_USERNAME": "",
        "BITBUCKET_APP_PASSWORD": "",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        client = _make_client()
        assert isinstance(client, httpx.AsyncClient)
        assert client.auth is None
        assert client.headers.get("Authorization") == "Bearer regular_oauth_token_67890"


def test_make_client_with_app_password():
    """Verify BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD uses Basic Auth."""
    custom_env = {
        "BITBUCKET_TOKEN": "",
        "ATLASSIAN_USERNAME": "",
        "BITBUCKET_USERNAME": "test_user",
        "BITBUCKET_APP_PASSWORD": "app_password_abcde",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        client = _make_client()
        assert isinstance(client, httpx.AsyncClient)
        assert isinstance(client.auth, httpx.BasicAuth)
        assert client.auth._auth_header == _get_expected_auth_header("test_user", "app_password_abcde")


def test_make_client_with_no_credentials():
    """Verify public repos (no credentials) return an unauthenticated client."""
    custom_env = {
        "BITBUCKET_TOKEN": "",
        "ATLASSIAN_USERNAME": "",
        "BITBUCKET_USERNAME": "",
        "BITBUCKET_APP_PASSWORD": "",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        client = _make_client()
        assert isinstance(client, httpx.AsyncClient)
        assert client.auth is None
        assert "Authorization" not in client.headers
