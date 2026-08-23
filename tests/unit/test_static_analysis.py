from __future__ import annotations

"""Unit tests for the deterministic static-analysis tool.

Regression focus: the validator was reporting a CRITICAL syntax error on every
file because the closing markdown ``` fence in the ingested ``code_logic`` blob
was left in the source (a trailing blank line stopped the fence stripper), and
``[TRUNCATED: …]`` placeholders were being parsed as if they were real code.
"""
from types import SimpleNamespace

from agent_guardian.tools.static_analysis_tool import (
    run_static_analysis,
    _strip_fences,
    _is_placeholder,
    _parse_code_logic,
    _collect_sources,
)


def _ctx(state):
    return SimpleNamespace(state=state)


# --------------------------------------------------------------------------- #
# _strip_fences — the core bug
# --------------------------------------------------------------------------- #
def test_strip_fences_handles_trailing_blank_line_after_close():
    """Ingestion appends a leading newline to the next block, which lands as a
    trailing blank line on this file. The closing ``` must still be removed."""
    blob = "```python\nimport os\nx = 1\n```\n"
    assert _strip_fences(blob) == "import os\nx = 1"


def test_strip_fences_handles_blank_line_before_open():
    blob = "\n```python\nx = 1\n```"
    assert _strip_fences(blob) == "x = 1"


def test_strip_fences_no_fence_is_noop():
    assert _strip_fences("x = 1\ny = 2") == "x = 1\ny = 2"


def test_parsed_fenced_code_compiles_without_syntax_error():
    """End-to-end: a fenced block from code_logic must yield clean, parseable
    source — no leftover ``` producing a bogus syntax error."""
    code_logic = "\n--- app/main.py ---\n```python\nimport os\n\n\ndef run():\n    return os.getcwd()\n```\n"
    files = _parse_code_logic(code_logic)
    assert len(files) == 1
    name, src = files[0]
    assert name == "app/main.py"
    assert "```" not in src
    compile(src, name, "exec")  # raises SyntaxError if the fence leaked through


def test_run_static_analysis_no_false_syntax_errors_on_clean_code():
    code_logic = (
        "\n--- a.py ---\n```python\nimport os\n\n\ndef run():\n    return os.getcwd()\n```\n"
        "\n--- b.py ---\n```python\nVALUE = 42\n```\n"
    )
    result = run_static_analysis(_ctx({"code_logic": code_logic}))
    assert result["status"] == "success"
    assert result["files_analyzed"] == 2
    assert result["syntax_errors"] == 0


# --------------------------------------------------------------------------- #
# Placeholder handling
# --------------------------------------------------------------------------- #
def test_is_placeholder_detects_markers():
    assert _is_placeholder("[TRUNCATED: File omitted to stay within token limits]")
    assert _is_placeholder("  [INGESTION_FAILED] nothing fetched")
    assert _is_placeholder("[SYSTEM ERROR: bad zip]")
    assert not _is_placeholder("import os\n# [TRUNCATED] in a comment is fine")


def test_truncated_placeholders_are_skipped_not_flagged():
    code_logic = (
        "\n--- real.py ---\n```python\nx = 1\n```\n"
        "\n--- omitted.py ---\n[TRUNCATED: File omitted to stay within token limits]\n"
    )
    result = run_static_analysis(_ctx({"code_logic": code_logic}))
    assert result["status"] == "success"
    assert result["files_analyzed"] == 1  # only real.py
    assert result["syntax_errors"] == 0


def test_all_placeholders_reports_no_code():
    code_logic = (
        "\n--- a.py ---\n[TRUNCATED: File omitted to stay within token limits]\n"
        "\n--- b.py ---\n[TRUNCATED: File omitted to stay within token limits]\n"
    )
    result = run_static_analysis(_ctx({"code_logic": code_logic}))
    assert result["status"] == "no_code"
    assert result["files_analyzed"] == 0


# --------------------------------------------------------------------------- #
# Real detections still fire
# --------------------------------------------------------------------------- #
def test_real_syntax_error_is_detected():
    code_logic = "\n--- broken.py ---\n```python\ndef f(:\n    pass\n```\n"
    result = run_static_analysis(_ctx({"code_logic": code_logic}))
    assert result["syntax_errors"] == 1
    assert any(f["severity"] == "CRITICAL" for f in result["findings"])


def test_dangerous_eval_detected():
    code_logic = "\n--- danger.py ---\n```python\nuser = input()\neval(user)\n```\n"
    result = run_static_analysis(_ctx({"code_logic": code_logic}))
    rules = " ".join(f["rule"] for f in result["findings"])
    assert "eval" in rules


# --------------------------------------------------------------------------- #
# Source selection
# --------------------------------------------------------------------------- #
def test_collect_sources_prefers_disk_over_truncated_code_logic(tmp_path):
    """The deterministic analyzer should read the full extracted source from
    disk rather than the token-truncated code_logic blob."""
    src_dir = tmp_path / "source"
    (src_dir / "pkg").mkdir(parents=True)
    (src_dir / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (src_dir / "root.py").write_text("y = 2\n", encoding="utf-8")

    state = {
        "source_artifact_path": str(src_dir),
        "code_logic": "\n--- only_one.py ---\n```python\nz = 3\n```\n",
    }
    files, origin = _collect_sources(_ctx(state))
    assert origin == "source_artifact_path"
    names = {n for n, _ in files}
    assert names == {"pkg/mod.py", "root.py"}


def test_collect_sources_falls_back_to_code_logic_without_disk():
    state = {"code_logic": "\n--- a.py ---\n```python\nx = 1\n```\n"}
    files, origin = _collect_sources(_ctx(state))
    assert origin == "code_logic"
    assert [n for n, _ in files] == ["a.py"]


def test_no_state_reports_no_code():
    result = run_static_analysis(_ctx({}))
    assert result["status"] == "no_code"
