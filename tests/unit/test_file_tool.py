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
