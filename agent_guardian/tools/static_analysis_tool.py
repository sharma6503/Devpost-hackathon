from __future__ import annotations

"""
static_analysis_tool.py — Deterministic, execution-free code validation.

Replaces the sandboxed ``BuiltInCodeExecutor`` (which could only run isolated
snippets it wrote itself, never the audited repo, and was the pipeline's most
fragile node). Instead this runs real, deterministic analyzers over the
ingested source and returns structured findings the validator agent interprets:

  * Python ``compile()``  → syntax / parse errors (CRITICAL, fully precise)
  * Python ``ast`` walk   → dangerous calls (eval/exec/os.system/shell=True),
                            insecure deserialization (pickle/marshal/yaml.load),
                            disabled TLS verification, weak hashes, hardcoded
                            secrets, bare/swallowed excepts, mutable defaults
  * pyflakes / bandit     → used opportunistically *if installed* (enrichment)
  * generic regex pass    → secrets / private keys / dangerous patterns across
                            non-Python files too (JS/TS/Go/etc.)

Everything is best-effort and exception-safe: the tool never raises, so it can
never break the pipeline.
"""

import ast
import logging
import os
import re
from typing import Any, Optional

from google.adk.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)

# Severity ranking (high → low) for sorting/aggregation.
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

_MAX_FILE_CHARS = 200_000  # skip AST on absurdly large single files
_MAX_FINDINGS = 250  # cap returned findings to keep output bounded
_MAX_REPORT_ROWS = 120  # cap rows rendered in the markdown table

_SECRET_NAME_RE = re.compile(
    r"(?i)(pass(word|wd)?|secret|api[_-]?key|apikey|access[_-]?key|"
    r"auth[_-]?token|client[_-]?secret|private[_-]?key|token)$"
)
_PLACEHOLDER_RE = re.compile(
    r"(?i)^(|changeme|example|test|dummy|placeholder|your[_-].*|xxx+|<.*>|"
    r"none|null|todo|fixme|os\.environ.*)$"
)

# Generic cross-language patterns (used on every file, including non-Python).
_GENERIC_PATTERNS = [
    (
        "private-key",
        "HIGH",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ),
    ("aws-access-key", "HIGH", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "hardcoded-secret",
        "HIGH",
        re.compile(
            r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|client[_-]?secret)"
            r"\s*[:=]\s*[\"'][^\"'\s]{6,}[\"']"
        ),
    ),
]
_GENERIC_JS_DANGER = [
    ("js-eval", "HIGH", re.compile(r"(?<![\w.])eval\s*\(")),
    ("js-child-process", "HIGH", re.compile(r"child_process|exec\s*\(|execSync\s*\(")),
    ("js-inner-html", "MEDIUM", re.compile(r"\.innerHTML\s*=")),
]

_HEADER_RE = re.compile(r"^---\s+(.*?)\s+---\s*$")
_PY_EXT = (".py",)
_CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".java", ".php", ".sh")
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".adk",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
}


# --------------------------------------------------------------------------- #
# Source acquisition
# --------------------------------------------------------------------------- #
def _strip_fences(src: str) -> str:
    """Remove a surrounding markdown ``` code fence from an ingested file block.

    Tolerates blank lines around the fences. This matters because ingestion
    builds each block as ``"\\n--- name ---\\n" + content``, so the next block's
    leading newline lands as a *trailing blank line* on the previous file — if we
    only inspected the very last line we'd leave the closing ``` in place and
    ``ast.parse`` would report a bogus syntax error at that line.
    """
    lines = src.splitlines()
    # Leading: drop blank lines, then a single opening fence, then blanks again.
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].lstrip().startswith("```"):
        lines.pop(0)
    # Trailing: drop blank lines, then a single closing fence, then blanks again.
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].lstrip().startswith("```"):
        lines.pop()
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# Placeholder markers ingestion inserts for omitted/oversized files — these are
# not source code and must never be handed to ast.parse (they'd report as syntax
# errors). Matched case-insensitively at the very start of a file's content.
_PLACEHOLDER_PREFIXES = (
    "[TRUNCATED",
    "[INGESTION_FAILED",
    "[SYSTEM ERROR",
    "[SYSTEM_NOTE",
    "[CONFLUENCE_UNAVAILABLE",
)


def _is_placeholder(source: str) -> bool:
    head = source.lstrip()
    return head.upper().startswith(_PLACEHOLDER_PREFIXES)


def _parse_code_logic(blob: str) -> list[tuple[str, str]]:
    """Split the ingested ``code_logic`` blob into (filename, source) pairs."""
    files: list[tuple[str, list[str]]] = []
    cur_name: Optional[str] = None
    cur: list[str] = []
    for line in (blob or "").splitlines():
        m = _HEADER_RE.match(line)
        if m:
            if cur_name is not None:
                files.append((cur_name, cur))
            cur_name = m.group(1).strip()
            cur = []
        elif cur_name is not None:
            cur.append(line)
    if cur_name is not None:
        files.append((cur_name, cur))
    return [(name, _strip_fences("\n".join(buf))) for name, buf in files]


def _walk_source_dir(root: str) -> list[tuple[str, str]]:
    """Walk an extracted-source directory for code files (fallback path)."""
    out: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(_CODE_EXT):
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    out.append((os.path.relpath(full, root).replace("\\", "/"), f.read()))
            except Exception as e:
                logger.warning(f"_walk_source_dir: could not read {full}: {e}")
                continue
            if len(out) >= 2000:
                return out
    return out


def _collect_sources(tool_context: ToolContext) -> tuple[list[tuple[str, str]], str]:
    """Return (files, origin).

    Prefer the full extracted source on disk (``source_artifact_path``): it is
    complete (the LLM-facing ``code_logic`` blob is truncated to a token budget
    that doesn't apply to deterministic analysis) and is read straight from real
    files, avoiding any markdown-fence parsing. Fall back to the curated
    ``code_logic`` blob — e.g. for GitHub ingestion, which has no extracted dir.
    """
    state = getattr(tool_context, "state", {}) or {}
    sap = state.get("source_artifact_path")
    if sap and os.path.isdir(sap):
        files = _walk_source_dir(sap)
        if files:
            return files, "source_artifact_path"
    blob = state.get("code_logic") or ""
    if isinstance(blob, str) and blob.strip() and not blob.startswith("[INGESTION_FAILED]"):
        files = _parse_code_logic(blob)
        if files:
            return files, "code_logic"
    return [], "none"


# --------------------------------------------------------------------------- #
# Python AST analysis
# --------------------------------------------------------------------------- #
def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _kw(node: ast.Call, name: str) -> Optional[ast.AST]:
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true(node: Optional[ast.AST]) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_false(node: Optional[ast.AST]) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _analyze_python(filename: str, source: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(line: int, severity: str, rule: str, message: str) -> None:
        findings.append(
            {
                "file": filename,
                "line": line,
                "severity": severity,
                "rule": rule,
                "message": message,
            }
        )

    if len(source) > _MAX_FILE_CHARS:
        return findings  # too large to parse safely; skip (regex pass still applies)

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        add(
            e.lineno or 0,
            "CRITICAL",
            "syntax-error",
            f"SyntaxError: {e.msg} (col {e.offset})",
        )
        return findings
    except Exception as e:  # pragma: no cover - defensive
        add(0, "MEDIUM", "parse-error", f"Could not parse file: {e}")
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _dotted_name(node.func)
            ln = getattr(node, "lineno", 0)
            short = fn.split(".")[-1]
            if short in ("eval", "exec") and fn in ("eval", "exec"):
                add(
                    ln,
                    "HIGH",
                    "dangerous-eval-exec",
                    f"Use of `{fn}()` enables arbitrary code execution.",
                )
            elif fn == "__import__":
                add(ln, "MEDIUM", "dynamic-import", "Dynamic `__import__()` call.")
            elif fn in ("os.system", "os.popen"):
                add(ln, "HIGH", "shell-exec", f"`{fn}()` runs a shell command.")
            elif fn in (
                "pickle.load",
                "pickle.loads",
                "cPickle.loads",
                "marshal.loads",
                "dill.loads",
            ):
                add(
                    ln,
                    "HIGH",
                    "insecure-deserialization",
                    f"`{fn}()` deserializes untrusted data (RCE risk).",
                )
            elif fn in ("yaml.load",) and not any(
                isinstance(k.value, ast.Attribute) and "Safe" in (k.value.attr or "")
                for k in node.keywords
                if k.arg == "Loader"
            ):
                add(
                    ln,
                    "HIGH",
                    "unsafe-yaml-load",
                    "`yaml.load()` without SafeLoader can execute arbitrary objects.",
                )
            elif (
                short in ("call", "run", "Popen", "check_call", "check_output")
                and (fn.startswith("subprocess.") or fn.startswith("sp."))
                and _is_true(_kw(node, "shell"))
            ):
                add(
                    ln,
                    "HIGH",
                    "subprocess-shell-true",
                    f"`{fn}(shell=True)` is vulnerable to shell injection.",
                )
            elif fn in ("hashlib.md5", "hashlib.sha1"):
                add(
                    ln,
                    "MEDIUM",
                    "weak-hash",
                    f"`{fn}()` is a weak hash; avoid for security-sensitive use.",
                )
            elif _is_false(_kw(node, "verify")) and (
                "request" in fn.lower() or fn.split(".")[0] in ("requests", "httpx", "session")
            ):
                add(
                    ln,
                    "HIGH",
                    "tls-verify-disabled",
                    f"`{fn}(verify=False)` disables TLS certificate verification.",
                )

        elif isinstance(node, ast.ExceptHandler):
            ln = getattr(node, "lineno", 0)
            if node.type is None:
                add(
                    ln,
                    "MEDIUM",
                    "bare-except",
                    "Bare `except:` catches everything, including SystemExit/KeyboardInterrupt.",
                )
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                add(
                    ln,
                    "MEDIUM",
                    "swallowed-exception",
                    "Exception silently swallowed with `pass`.",
                )

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ln = getattr(node, "lineno", 0)
            for d in list(node.args.defaults) + list(node.args.kw_defaults):
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    add(
                        ln,
                        "LOW",
                        "mutable-default",
                        f"Function `{node.name}` has a mutable default argument.",
                    )
                    break

        elif isinstance(node, ast.Assign):
            ln = getattr(node, "lineno", 0)
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                val = node.value.value
                if 6 <= len(val) and not _PLACEHOLDER_RE.match(val.strip()):
                    for t in node.targets:
                        nm = _dotted_name(t)
                        leaf = nm.split(".")[-1] if nm else ""
                        if leaf and _SECRET_NAME_RE.search(leaf):
                            add(
                                ln,
                                "HIGH",
                                "hardcoded-secret",
                                f"Possible hardcoded secret assigned to `{nm}`.",
                            )
                            break
    return findings


# --------------------------------------------------------------------------- #
# Optional enrichment (only if the packages are installed)
# --------------------------------------------------------------------------- #
def _pyflakes_findings(filename: str, source: str) -> list[dict[str, Any]]:
    try:
        import io
        from pyflakes.api import check
        from pyflakes.reporter import Reporter
    except ImportError:
        return []
    out_buf, err_buf = io.StringIO(), io.StringIO()
    try:
        check(source, filename, Reporter(out_buf, err_buf))
    except Exception as e:
        logger.warning(f"pyflakes enrichment failed for {filename}: {e}")
        return []
    findings = []
    for line in out_buf.getvalue().splitlines():
        # format: filename:line:col: message
        m = re.match(r"^.*?:(\d+):(?:\d+:)?\s*(.*)$", line)
        if m:
            findings.append(
                {
                    "file": filename,
                    "line": int(m.group(1)),
                    "severity": "MEDIUM",
                    "rule": "pyflakes",
                    "message": m.group(2),
                }
            )
    return findings


# Map bandit severity → our scale.
_BANDIT_SEVERITY = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}


def _bandit_findings(py_files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Run bandit's security checks (if installed) over the Python sources.

    Bandit's stable API discovers files from disk, so we materialize the parsed
    sources into a temp dir, scan once, then map results back to the original
    relative filenames. No-op (returns []) if bandit isn't installed.
    """
    if not py_files:
        return []
    try:
        from bandit.core import config as b_config
        from bandit.core import manager as b_manager
    except ImportError:
        return []

    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="ag_bandit_")
    name_map: dict[str, str] = {}
    try:
        for rel, src in py_files:
            safe_rel = rel.replace("\\", "/").lstrip("/")
            dest = os.path.join(tmp, *safe_rel.split("/"))
            try:
                os.makedirs(os.path.dirname(dest) or tmp, exist_ok=True)
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(src)
                name_map[os.path.normcase(os.path.abspath(dest))] = rel
            except Exception as e:
                logger.warning(f"_bandit_findings: could not materialize {rel}: {e}")
                continue

        mgr = b_manager.BanditManager(b_config.BanditConfig(), "file")
        mgr.discover_files([tmp], recursive=True)
        mgr.run_tests()

        findings = []
        for issue in mgr.get_issue_list():
            key = os.path.normcase(os.path.abspath(getattr(issue, "fname", "")))
            fname = name_map.get(key, getattr(issue, "fname", ""))
            sev = _BANDIT_SEVERITY.get(str(getattr(issue, "severity", "")).upper(), "MEDIUM")
            findings.append(
                {
                    "file": fname,
                    "line": int(getattr(issue, "lineno", 0) or 0),
                    "severity": sev,
                    "rule": f"bandit-{getattr(issue, 'test_id', '?')}",
                    "message": str(getattr(issue, "text", "Security issue")).splitlines()[0],
                }
            )
        return findings
    except Exception as e:  # bandit internals vary across versions — fail closed
        logger.warning(f"bandit enrichment failed: {e}")
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Generic regex pass (all files)
# --------------------------------------------------------------------------- #
def _regex_findings(filename: str, source: str, is_python: bool) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    patterns = list(_GENERIC_PATTERNS)
    if not is_python:  # AST already covers Python; add JS-ish danger for others
        if filename.endswith((".js", ".jsx", ".ts", ".tsx")):
            patterns += _GENERIC_JS_DANGER
    seen: set[tuple[int, str]] = set()
    for i, line in enumerate(source.splitlines(), start=1):
        for rule, severity, rx in patterns:
            if rx.search(line) and (i, rule) not in seen:
                seen.add((i, rule))
                findings.append(
                    {
                        "file": filename,
                        "line": i,
                        "severity": severity,
                        "rule": rule,
                        "message": f"Pattern match: {rule}.",
                    }
                )
    return findings


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def _render_report(
    files_n: int,
    py_n: int,
    origin: str,
    findings: list[dict[str, Any]],
    counts: dict[str, int],
) -> str:
    lines = [
        "## Static Analysis Results (execution-free, deterministic)",
        "",
        f"- Files analyzed: **{files_n}** ({py_n} Python) — source: `{origin}`",
        f"- Findings: **{sum(counts.values())}** "
        + " · ".join(f"{k}={counts.get(k, 0)}" for k in _SEVERITY_ORDER if counts.get(k)),
        "",
    ]
    if not findings:
        lines.append("No static-analysis findings detected. ✅")
        return "\n".join(lines)
    lines += [
        "| Severity | File:Line | Rule | Detail |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for f in findings[:_MAX_REPORT_ROWS]:
        detail = f["message"].replace("|", "\\|")
        lines.append(f"| {f['severity']} | `{f['file']}:{f['line']}` | {f['rule']} | {detail} |")
    if len(findings) > _MAX_REPORT_ROWS:
        lines.append(f"\n_+{len(findings) - _MAX_REPORT_ROWS} more findings omitted from this table._")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Public tool
# --------------------------------------------------------------------------- #
def run_static_analysis(tool_context: ToolContext) -> dict:
    """Run deterministic, execution-free static analysis on the ingested codebase.

    Analyzes the code already loaded into session state (no sandbox, no code
    execution). Detects syntax/parse errors, dangerous calls (eval/exec,
    os.system, subprocess shell=True), insecure deserialization, disabled TLS
    verification, weak hashes, hardcoded secrets, bare/swallowed exceptions, and
    mutable default arguments for Python; plus a cross-language regex pass for
    secrets and private keys. Findings are precise and cite `file:line`.

    Call this tool once, then base your validation report on its findings.

    Returns:
        A dict with:
          - "status": "success" | "no_code" | "error"
          - "files_analyzed", "python_files", "syntax_errors": counts (int)
          - "severity_counts": dict of CRITICAL/HIGH/MEDIUM/LOW/INFO → count
          - "findings": list of {file, line, severity, rule, message}
          - "report": a ready-to-read markdown summary of all findings
          - "message": human-readable status
    """
    try:
        files, origin = _collect_sources(tool_context)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"run_static_analysis: source collection failed: {e}")
        return {
            "status": "error",
            "files_analyzed": 0,
            "python_files": 0,
            "syntax_errors": 0,
            "severity_counts": {},
            "findings": [],
            "report": "Static analysis could not read the source.",
            "message": f"Source collection failed: {e}",
        }

    if not files:
        return {
            "status": "no_code",
            "files_analyzed": 0,
            "python_files": 0,
            "syntax_errors": 0,
            "severity_counts": {},
            "findings": [],
            "report": "No source code was available to analyze.",
            "message": "No code_logic or source_artifact_path found in state.",
        }

    all_findings: list[dict[str, Any]] = []
    py_files: list[tuple[str, str]] = []
    analyzed_n = 0
    for filename, source in files:
        if not source.strip() or _is_placeholder(source):
            # Empty, or an ingestion placeholder (e.g. "[TRUNCATED: …]") — not
            # real source, so analyzing it would only yield false syntax errors.
            continue
        analyzed_n += 1
        is_python = filename.endswith(_PY_EXT)
        try:
            if is_python:
                py_files.append((filename, source))
                all_findings.extend(_analyze_python(filename, source))
                all_findings.extend(_pyflakes_findings(filename, source))
            all_findings.extend(_regex_findings(filename, source, is_python))
        except Exception as e:  # pragma: no cover - never let one file break the tool
            logger.warning(f"run_static_analysis: analysis failed for {filename}: {e}")

    py_n = len(py_files)

    # Every "file" was an ingestion placeholder / empty — there was no real
    # source to validate. Report that honestly instead of a bogus clean pass.
    if analyzed_n == 0:
        return {
            "status": "no_code",
            "files_analyzed": 0,
            "python_files": 0,
            "syntax_errors": 0,
            "severity_counts": {},
            "findings": [],
            "report": "No analyzable source code was available (all ingested entries were truncated or placeholders).",
            "message": "Ingested content contained no analyzable source files.",
        }

    all_findings.extend(_bandit_findings(py_files))  # one pass over all Python files

    syntax_errors = sum(1 for f in all_findings if f["rule"] == "syntax-error")

    # Merge findings on the same file:line (e.g. our AST check and bandit both
    # flagging one `eval()`) into a single row: highest severity wins, rules and
    # messages are combined. Keeps the report and severity counts honest.
    merged: dict[tuple[str, int], dict[str, Any]] = {}
    for f in all_findings:
        key = (f["file"], f["line"])
        m = merged.get(key)
        if m is None:
            merged[key] = {
                "file": f["file"],
                "line": f["line"],
                "severity": f["severity"],
                "_rules": {f["rule"]},
                "_msgs": [f["message"]],
            }
        else:
            m["_rules"].add(f["rule"])
            if f["message"] not in m["_msgs"]:
                m["_msgs"].append(f["message"])
            if _SEVERITY_ORDER.get(f["severity"], 9) < _SEVERITY_ORDER.get(m["severity"], 9):
                m["severity"] = f["severity"]

    all_findings = [
        {
            "file": m["file"],
            "line": m["line"],
            "severity": m["severity"],
            "rule": ", ".join(sorted(m["_rules"])),
            "message": " | ".join(m["_msgs"]),
        }
        for m in merged.values()
    ]

    # Sort by severity then file, cap, and aggregate counts.
    all_findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    capped = all_findings[:_MAX_FINDINGS]
    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    report = _render_report(analyzed_n, py_n, origin, capped, counts)
    logger.info(
        f"run_static_analysis: {analyzed_n} files ({py_n} py), "
        f"{len(all_findings)} findings ({syntax_errors} syntax errors)."
    )
    return {
        "status": "success",
        "files_analyzed": analyzed_n,
        "python_files": py_n,
        "syntax_errors": syntax_errors,
        "severity_counts": counts,
        "findings": capped,
        "report": report,
        "message": (f"Analyzed {analyzed_n} files; found {len(all_findings)} issues ({syntax_errors} syntax errors)."),
    }
