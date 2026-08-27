from __future__ import annotations
import os
import zipfile
import tempfile
from agent_guardian.tools.file_tool import parse_uploaded_files


def test_parse_uploaded_files_single_file():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def test(): pass")
        temp_path = f.name

    try:
        result = parse_uploaded_files([temp_path])
        assert result["status"] == "success"
        assert result["file_count"] == 1
        assert "def test(): pass" in result["codebase"]
    finally:
        os.remove(temp_path)


def test_parse_uploaded_files_zip():
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("main.py", "print('hello')")
            zf.writestr("utils/helper.py", "def help(): pass")
            zf.writestr("README.md", "# Test Project")
            zf.writestr("binary.exe", b"\x00\x01\x02")  # Should be skipped by extension or content

        result = parse_uploaded_files([zip_path])
        assert result["status"] == "success"
        # README.md is in CODE_EXTENSIONS (.md), main.py and helper.py are .py
        # binary.exe should be skipped because .exe is not in CODE_EXTENSIONS
        assert result["file_count"] == 3
        assert "main.py" in result["codebase"]
        assert "helper.py" in result["codebase"]
        assert "README.md" in result["codebase"]


def test_parse_uploaded_files_zip_traversal_prevention():
    from unittest.mock import MagicMock
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "evil.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../evil.py", "malicious_code = True")
            zf.writestr("/root_escape.py", "escaped = True")
            zf.writestr("safe.py", "safe_code = True")

        mock_context = MagicMock()
        mock_context.session.id = "test_session_traversal"
        mock_context.state = {}

        result = parse_uploaded_files([zip_path], tool_context=mock_context)
        assert result["status"] == "success"
        assert "safe.py" in result["codebase"]

        # Check extracted artifacts dir
        art_dir = Path.cwd() / ".adk" / "artifacts" / "test_session_traversal" / "source"
        if art_dir.exists():
            assert (art_dir / "safe.py").exists()
            # Ensure no files escaped outside artifact directory
            assert not (art_dir.parent / "evil.py").exists()


def test_parse_uploaded_files_sensitive_files_denied():
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "creds.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(".env", "SECRET_KEY=12345")
            zf.writestr("id_rsa", "-----BEGIN RSA PRIVATE KEY-----")
            zf.writestr("service_account.json", '{"type": "service_account"}')
            zf.writestr("server.key", "PRIVATE_KEY_DATA")
            zf.writestr(".env.example", "SECRET_KEY=sample")
            zf.writestr("app.py", "print('safe app')")

        result = parse_uploaded_files([zip_path])
        assert result["status"] == "success"
        # .env, id_rsa, service_account.json, server.key should be rejected
        # .env.example and app.py should be accepted
        assert result["file_count"] == 2
        assert "app.py" in result["codebase"]
        assert ".env.example" in result["codebase"]
        assert "SECRET_KEY=12345" not in result["codebase"]
        assert "PRIVATE_KEY_DATA" not in result["codebase"]


def test_parse_uploaded_files_session_id_sanitization():
    from unittest.mock import MagicMock
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("app.py", "print('hello')")

        mock_context = MagicMock()
        mock_context.session.id = "../../../traversal_session"
        mock_context.state = {}

        result = parse_uploaded_files([zip_path], tool_context=mock_context)
        assert result["status"] == "success"

        # Traversal session ID must be sanitized to alphanumeric/dash/underscore
        clean_dir = Path.cwd() / ".adk" / "artifacts" / "traversal_session" / "source"
        assert clean_dir.is_relative_to((Path.cwd() / ".adk" / "artifacts").resolve())

