import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from google.adk.artifacts import InMemoryArtifactService
from agent_guardian.utils.artifact_factory import get_artifact_service
from agent_guardian.tools.artifact_tool import read_artifact_file, save_artifact_file


def test_get_artifact_service_default_inmemory():
    with patch.dict(os.environ, {}, clear=True):
        service = get_artifact_service()
        assert isinstance(service, InMemoryArtifactService)


def test_get_artifact_service_gcs_uri():
    with patch.dict(os.environ, {"ARTIFACT_SERVICE_URI": "gs://test-artifacts-bucket"}, clear=True):
        with patch("google.adk.artifacts.GcsArtifactService") as mock_gcs_cls:
            mock_gcs_cls.return_value = MagicMock()
            _ = get_artifact_service()
            mock_gcs_cls.assert_called_once_with(bucket_name="test-artifacts-bucket")


def test_get_artifact_service_bucket_name_arg():
    with patch.dict(os.environ, {}, clear=True):
        with patch("google.adk.artifacts.GcsArtifactService") as mock_gcs_cls:
            mock_gcs_cls.return_value = MagicMock()
            _ = get_artifact_service(bucket_name="agentguardian-prod-artifacts")
            mock_gcs_cls.assert_called_once_with(bucket_name="agentguardian-prod-artifacts")


def test_get_artifact_service_file_uri():
    with patch.dict(os.environ, {"ARTIFACT_SERVICE_URI": "file:///tmp/artifacts"}, clear=True):
        with patch("google.adk.artifacts.FileArtifactService") as mock_file_cls:
            mock_file_cls.return_value = MagicMock()
            _ = get_artifact_service()
            mock_file_cls.assert_called_once_with(root_dir="/tmp/artifacts")


@pytest.mark.asyncio
async def test_save_artifact_file_success():
    mock_context = MagicMock()
    mock_context.save_artifact = AsyncMock(return_value=1)

    result = await save_artifact_file(
        filename="report.html",
        content="<html><body>Audit Report</body></html>",
        mime_type="text/html",
        tool_context=mock_context,
    )

    assert result["status"] == "success"
    assert result["filename"] == "report.html"
    assert result["version"] == 1
    assert result["bytes_saved"] > 0
    mock_context.save_artifact.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_artifact_file_no_context():
    result = await save_artifact_file(
        filename="report.html",
        content="test",
        tool_context=None,
    )
    assert result["status"] == "error"
    assert "Tool context unavailable" in result["message"]


@pytest.mark.asyncio
async def test_read_artifact_file_success():
    mock_context = MagicMock()
    mock_part = MagicMock()
    mock_part.inline_data.data = b"def test(): pass"
    mock_context.load_artifact = AsyncMock(return_value=mock_part)

    result = await read_artifact_file(filename="main.py", tool_context=mock_context)
    assert result["status"] == "success"
    assert "def test(): pass" in result["codebase"]
    assert result["file_count"] == 1


@pytest.mark.asyncio
async def test_read_artifact_file_zip_success():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("server.py", "app = Flask(__name__)")
        zf.writestr("config.json", '{"debug": false}')

    mock_context = MagicMock()
    mock_part = MagicMock()
    mock_part.inline_data.data = buf.getvalue()
    mock_context.load_artifact = AsyncMock(return_value=mock_part)

    result = await read_artifact_file(filename="project.zip", tool_context=mock_context)
    assert result["status"] == "success"
    assert result["file_count"] == 2
    assert "server.py" in result["codebase"]
    assert "config.json" in result["codebase"]


@pytest.mark.asyncio
async def test_read_artifact_file_traversal():
    mock_context = MagicMock()
    result = await read_artifact_file(filename="../..", tool_context=mock_context)
    assert result["status"] == "error"
    assert "Invalid filename" in result["message"]


@pytest.mark.asyncio
async def test_save_artifact_file_payload_limit():
    mock_context = MagicMock()
    oversized = "a" * (11 * 1024 * 1024)  # 11MB
    result = await save_artifact_file(
        filename="huge.txt",
        content=oversized,
        tool_context=mock_context,
    )
    assert result["status"] == "error"
    assert "exceeds maximum allowed size" in result["message"]
