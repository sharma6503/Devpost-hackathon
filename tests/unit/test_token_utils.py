from __future__ import annotations
from agent_guardian.utils.token_utils import TokenManager


def test_token_manager_count_heuristic():
    # Test fallback heuristic (client-less)
    tm = TokenManager(model_name="test-model")
    text = "def hello(): pass"  # 17 chars
    # heuristic is len // 3 = 5
    count = tm.count_tokens(text)
    assert count == 5


def test_token_manager_truncate_to_budget():
    tm = TokenManager(model_name="test-model")
    parts = [
        "part one",  # 8 chars -> 2 tokens
        "part two",  # 8 chars -> 2 tokens
        "part three",  # 10 chars -> 3 tokens
    ]
    # Total tokens approx: 2 + 2 + 3 = 7

    # Budget of 6 should keep first two parts (joined len 18 -> 6 tokens)
    result = tm.truncate_to_budget(parts, 6)
    assert "part one" in result
    assert "part two" in result
    assert "part three" not in result


def test_token_manager_is_over_budget():
    tm = TokenManager(model_name="test-model")
    text = "a" * 300  # 300 chars -> 100 tokens
    assert tm.is_over_budget(text, 50) is True
    assert tm.is_over_budget(text, 150) is False


def test_token_manager_use_vertex_parsing(monkeypatch):
    from unittest.mock import patch

    # Mock the Client constructor
    with patch("agent_guardian.utils.token_utils.Client") as mock_client:
        # Case 1: UPPERCASE 'TRUE'
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")

        TokenManager(model_name="test-model")
        mock_client.assert_called_with(vertexai=True, project="test-project", location="global")

        mock_client.reset_mock()

        # Case 2: lowercase 'true'
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
        TokenManager(model_name="test-model")
        mock_client.assert_called_with(vertexai=True, project="test-project", location="global")

        mock_client.reset_mock()

        # Case 3: Titlecase 'True'
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "True")
        TokenManager(model_name="test-model")
        mock_client.assert_called_with(vertexai=True, project="test-project", location="global")

        mock_client.reset_mock()

        # Case 4: string '1'
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
        TokenManager(model_name="test-model")
        mock_client.assert_called_with(vertexai=True, project="test-project", location="global")
