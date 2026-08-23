import os
from unittest.mock import patch
from agent_guardian.config import Config


def test_default_config_loading():
    """Verify default config values when no env vars are set."""
    with patch.dict(os.environ, {}, clear=True):
        config = Config()
        assert config.agent_settings.root_model == "gemini-3.7-flash"
        assert config.github_base_branch == "main"
        assert config.max_retries == 5
        assert config.max_file_size_kb == 10240


def test_env_var_override():
    """Verify that environment variables correctly override defaults."""
    custom_env = {
        "ROOT_MODEL": "custom-model",
        "GITHUB_TOKEN": "secret-token",
        "MAX_RETRIES": "10",
        "EVAL_PASS_THRESHOLD": "8",
    }
    with patch.dict(os.environ, custom_env):
        config = Config()
        assert config.agent_settings.root_model == "custom-model"
        assert config.github_token == "secret-token"
        assert config.max_retries == 10
        assert config.agent_settings.eval_pass_threshold == 8


def test_safety_config_property():
    """Verify that the safety_config property returns a valid GenerateContentConfig."""
    config = Config()
    safety = config.safety_config

    assert safety.http_options.retry_options.attempts == config.max_retries
    assert len(safety.safety_settings) == 4

    # Check a specific setting
    harassment = next(s for s in safety.safety_settings if s.category == "HARM_CATEGORY_HARASSMENT")
    assert harassment.threshold == "BLOCK_MEDIUM_AND_ABOVE"


def test_config_immutability_logic():
    """Verify we can create multiple config instances with different envs."""
    with patch.dict(os.environ, {"ROOT_MODEL": "model-a"}):
        config_a = Config()

    with patch.dict(os.environ, {"ROOT_MODEL": "model-b"}):
        config_b = Config()

    assert config_a.agent_settings.root_model == "model-a"
    assert config_b.agent_settings.root_model == "model-b"
