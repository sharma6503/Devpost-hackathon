from __future__ import annotations
import logging
import re
import ast
import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def scan_regex(file_content: str, patterns: List[str] = None) -> List[Dict[str, Any]]:
    """
    Scans file content for specific regex patterns using optimized line lookup.
    """
    if patterns is None:
        patterns = [
            r'(?i)(api[_-]?key|secret|password|token|auth|credential)["\']?\s*[:=]\s*["\']([^"\'\s]+)["\']',
            r"(?i)(AIza[0-9A-Za-z\\-_]{35})",  # Google API Key
            r"(?i)(sk-[a-zA-Z0-9]{48})",  # OpenAI Key
            r"(?i)([a-z0-9\.-]+@[a-z0-9\.-]+\.[a-z]{2,})",  # Email (PII)
        ]

    # Precompute line boundaries once
    line_starts = [0]
    for m in re.finditer(r"\n", file_content):
        line_starts.append(m.end())

    findings = []
    compiled_patterns = [re.compile(p) for p in patterns]

    # Cap line length to avoid catastrophic backtracking
    MAX_LINE_LEN = 4096
    lines = file_content.splitlines()
    for line_no, line in enumerate(lines, 1):
        if len(line) > MAX_LINE_LEN:
            continue  # skip pathological lines
        for cp in compiled_patterns:
            try:
                for match in cp.finditer(line):
                    findings.append(
                        {
                            "line": line_no,
                            "match": match.group(0),
                            "issue": "Sensitive pattern match detected",
                            "context": line.strip(),
                        }
                    )
            except Exception:
                continue
    return findings


def audit_dependencies(requirements_content: str) -> List[Dict[str, Any]]:
    """
    Audits requirements.txt content for unpinned versions.
    Checks if packages use strict '==' pinning.
    """
    findings = []
    lines = requirements_content.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Strict pinning check: must contain '==' and not contain other loose operators
        if "==" not in line:
            findings.append(
                {
                    "line": i + 1,
                    "package": line,
                    "issue": "Dependency version is not strictly pinned",
                    "recommendation": f"Pin the version for {line} using '==' (e.g., {line}==X.Y.Z)",
                }
            )
    return findings


def analyze_ast(file_content: str) -> List[Dict[str, Any]]:
    """
    Performs structural analysis on Python code using AST.
    Checks for: Health endpoints, Timeouts in network calls.
    """
    findings = []
    try:
        tree = ast.parse(file_content)
    except SyntaxError as e:
        return [{"issue": f"Syntax Error during AST analysis: {e}"}]

    has_health_endpoint = False

    for node in ast.walk(tree):
        # 1. Check for Route Decorators (FastAPI/Flask health check)
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    # Check for .get("/health") or similar
                    for arg in decorator.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            if any(x in arg.value.lower() for x in ["health", "status", "alive"]):
                                has_health_endpoint = True

        # 2. Check for Timeouts in tool calls or requests
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            # Common network/external call functions
            if func_name in (
                "get",
                "post",
                "request",
                "run_command",
                "run_async",
                "fetch",
                "call_tool",
            ):
                # Check for 'timeout' keyword argument
                has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                if not has_timeout:
                    findings.append(
                        {
                            "line": getattr(node, "lineno", 0),
                            "func": func_name,
                            "issue": "[REL-001] External call missing explicit timeout",
                            "recommendation": "Add a `timeout` parameter to ensure execution reliability.",
                        }
                    )

    if not has_health_endpoint:
        findings.append(
            {
                "issue": "[OBS-001] No health monitoring endpoint detected",
                "recommendation": "Expose a /health or /status route for observability.",
            }
        )

    return findings


def ast_grep_scan(
    file_path: str, file_content: str, pattern: str = None, rule_yaml: str = None
) -> List[Dict[str, Any]]:
    """
    Performs precision structural analysis using ast-grep (sg).
    Requires 'sg' to be installed in the environment.
    """
    if not (pattern or rule_yaml):
        return [{"issue": "No pattern or rule provided for ast-grep scan."}]

    findings = []
    lang = "python"  # Default
    ext = Path(file_path).suffix.lower()
    if ext in (".js", ".jsx"):
        lang = "javascript"
    elif ext in (".ts", ".tsx"):
        lang = "typescript"
    elif ext == ".go":
        lang = "go"
    elif ext == ".rs":
        lang = "rust"

    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    rule_path = None
    try:
        if pattern:
            # Inline pattern search
            cmd = [
                "sg",
                "run",
                "--pattern",
                pattern,
                "--lang",
                lang,
                "--json",
                tmp_path,
            ]
        else:
            # YAML rule search
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as rule_tmp:
                rule_tmp.write(rule_yaml)
                rule_path = rule_tmp.name
            cmd = ["sg", "scan", "--rule", rule_path, "--json", tmp_path]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)

        if result.returncode == 0 and result.stdout.strip():
            matches = json.loads(result.stdout)
            for m in matches:
                findings.append(
                    {
                        "line": m["range"]["start"]["line"] + 1,
                        "match": m["text"],
                        "issue": f"Structural match: {m.get('ruleId', 'pattern match')}",
                        "context": m["text"],
                    }
                )
        elif result.stderr:
            logger.debug(f"ast-grep stderr: {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.warning("ast-grep execution timed out after 15 seconds")
    except Exception as e:
        logger.warning(f"ast-grep execution failed: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if rule_path and os.path.exists(rule_path):
            os.remove(rule_path)

    return findings


def _parse_concatenated_files(file_content: str) -> List[tuple[str, str]]:
    """Parses a multi-file string separated by '--- filename ---' markers."""
    files = []
    if "--- " not in file_content or " ---" not in file_content:
        return []

    lines = file_content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and line.endswith(" ---"):
            fname = line[4:-4].strip()
            content_buf = []
            i += 1
            while i < len(lines) and not (lines[i].startswith("--- ") and lines[i].endswith(" ---")):
                content_buf.append(lines[i])
                i += 1
            files.append((fname, "\n".join(content_buf)))
            continue
        i += 1
    return files


def _strip_markdown_fences(content: str) -> str:
    """Removes leading/trailing markdown code fences."""
    clean = content.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.splitlines()[1:])
    if clean.endswith("```"):
        clean = "\n".join(clean.splitlines()[:-1])
    return clean


# Wrapper for the Governance Expert Agent to use
def scan_governance(
    file_path: str,
    file_content: str,
    check_type: str,
    pattern: Optional[str] = None,
    rule_yaml: Optional[str] = None,
    patterns: Optional[List[str]] = None,
) -> str:
    """
    Precision scanner for technical compliance.
    Decoupled from specific rule IDs to allow LLM-driven validation against live standards.
    """

    all_results = []

    # 1. Parse concatenated codebase blocks if necessary
    files_to_scan = _parse_concatenated_files(file_content)
    if not files_to_scan:
        files_to_scan = [(file_path, file_content)]

    # 2. Run selected scanner on each file
    for current_path, current_content in files_to_scan:
        clean_content = _strip_markdown_fences(current_content)

        results = []
        if check_type == "regex_scan":
            results = scan_regex(clean_content, patterns=patterns)
        elif check_type == "dep_scan":
            results = audit_dependencies(clean_content)
        elif check_type == "ast_check":
            if current_path.endswith(".py"):
                results = analyze_ast(clean_content)
        elif check_type == "ast_grep":
            results = ast_grep_scan(current_path, clean_content, pattern, rule_yaml)

        for r in results:
            if isinstance(r, dict):
                r["file"] = current_path
                all_results.append(r)

    if not all_results:
        return json.dumps({"status": "success", "message": "No technical issues detected by scanner."})

    return json.dumps(all_results, indent=2)
