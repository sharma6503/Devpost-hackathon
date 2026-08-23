import os
import sys
from unittest.mock import patch, MagicMock

from google.adk.sessions import InMemorySessionService
from agent_guardian.utils.session_factory import get_session_service


def test_get_session_service_default_inmemory():
    with patch.dict(os.environ, {}, clear=True):
        service = get_session_service()
        assert isinstance(service, InMemorySessionService)


def test_get_session_service_vertexai_type():
    env = {
        "SESSION_SERVICE_TYPE": "vertexai",
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
        "AGENT_ENGINE_ID": "test-engine-id",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("google.adk.sessions.VertexAiSessionService") as mock_vertex_cls:
            mock_vertex_cls.return_value = MagicMock()
            _ = get_session_service()
            mock_vertex_cls.assert_called_once_with(
                project="test-project",
                location="us-central1",
                agent_engine_id="test-engine-id",
            )


def test_get_session_service_session_location_override():
    env = {
        "SESSION_SERVICE_TYPE": "vertexai",
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_LOCATION": "global",
        "SESSION_LOCATION": "us-central1",
        "AGENT_ENGINE_ID": "test-engine-id",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("google.adk.sessions.VertexAiSessionService") as mock_vertex_cls:
            mock_vertex_cls.return_value = MagicMock()
            _ = get_session_service()
            mock_vertex_cls.assert_called_once_with(
                project="test-project",
                location="us-central1",
                agent_engine_id="test-engine-id",
            )


def test_get_session_service_agentengine_uri():
    with patch.dict(os.environ, {}, clear=True):
        with patch("google.adk.sessions.VertexAiSessionService") as mock_vertex_cls:
            mock_vertex_cls.return_value = MagicMock()
            _ = get_session_service(
                service_uri="agentengine://my-engine-id",
                project_id="proj-123",
                location="us-central1",
            )
            mock_vertex_cls.assert_called_once_with(
                project="proj-123",
                location="us-central1",
                agent_engine_id="my-engine-id",
            )


def test_get_session_service_database_uri():
    mock_db_cls = MagicMock()
    mock_mod = MagicMock()
    mock_mod.DatabaseSessionService = mock_db_cls

    with patch.dict(os.environ, {}, clear=True):
        with patch.dict(sys.modules, {"google.adk.sessions.database_session_service": mock_mod}):
            _ = get_session_service(service_uri="sqlite:///./test.db")
            mock_db_cls.assert_called_once_with(db_url="sqlite:///./test.db")
