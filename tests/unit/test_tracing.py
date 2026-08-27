from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from agent_guardian.config import Config
from agent_guardian.utils.tracing import is_cloud_tracing_enabled, setup_cloud_tracing


def test_is_cloud_tracing_enabled_env(monkeypatch):
    monkeypatch.delenv("ENABLE_CLOUD_TRACING", raising=False)
    monkeypatch.delenv("OTEL_TO_CLOUD", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", raising=False)
    assert not is_cloud_tracing_enabled()

    monkeypatch.setenv("ENABLE_CLOUD_TRACING", "true")
    assert is_cloud_tracing_enabled()

    monkeypatch.setenv("ENABLE_CLOUD_TRACING", "1")
    assert is_cloud_tracing_enabled()

    monkeypatch.setenv("ENABLE_CLOUD_TRACING", "false")
    assert not is_cloud_tracing_enabled()

    monkeypatch.delenv("ENABLE_CLOUD_TRACING", raising=False)
    monkeypatch.setenv("OTEL_TO_CLOUD", "true")
    assert is_cloud_tracing_enabled()


def test_setup_cloud_tracing_disabled():
    with patch.dict(os.environ, {"ENABLE_CLOUD_TRACING": "false"}, clear=False):
        result = setup_cloud_tracing(enable_cloud_tracing=False)
        assert result is False


def test_setup_cloud_tracing_missing_project(monkeypatch):
    monkeypatch.setenv("ENABLE_CLOUD_TRACING", "true")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    result = setup_cloud_tracing(project_id=None)
    assert result is False


def test_setup_cloud_tracing_success(monkeypatch):
    monkeypatch.setenv("ENABLE_CLOUD_TRACING", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-gcp-project")

    mock_hook = MagicMock()
    with patch("google.adk.telemetry.google_cloud.get_gcp_exporters", return_value=mock_hook) as mock_get:
        with patch("google.adk.telemetry.setup.maybe_set_otel_providers") as mock_set:
            result = setup_cloud_tracing(service_name="agent-guardian-test")
            assert result is True
            mock_get.assert_called_once_with(
                enable_cloud_tracing=True,
                enable_cloud_logging=False,
                enable_cloud_metrics=False,
            )
            mock_set.assert_called_once_with(otel_hooks_to_setup=[mock_hook])
            assert os.environ.get("OTEL_SERVICE_NAME") == "agent-guardian-test"


def test_config_cloud_tracing_fields(monkeypatch):
    monkeypatch.setenv("ENABLE_CLOUD_TRACING", "true")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-guardian-svc")
    cfg = Config()
    assert cfg.enable_cloud_tracing is True
    assert cfg.otel_service_name == "custom-guardian-svc"
