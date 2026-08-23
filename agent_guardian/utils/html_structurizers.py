from __future__ import annotations
import itertools
import re
import logging
from typing import Match
import markdown as _md

logger = logging.getLogger(__name__)

# --- Fenced-code masking -----------------------------------------------------
#
# Every segmentation regex in this module (finding headers, governance rule
# headers, label rows, item boundaries) is line-oriented and MUST NOT match
# lines inside fenced code blocks. Without masking, a requirements pin like
# "google-adk==0.1.25" inside a ``` fence becomes a bogus rule card
# (ids="google", title="adk"), and a label match in the middle of a fence
# splits it apart — the fence collapses, its language tag leaks as prose and
# in-code "#" comments render as giant headings.
#
# Fences are swapped for opaque \x00FENCE<n>\x00 tokens before any parsing and
# restored only at markdown-render time (_md_render).

_FENCED_CODE_RE = re.compile(r"(`{3,}|~{3,})[^\n]*\n.*?\1", re.DOTALL)
_FENCE_TOKEN_RE = re.compile(r"\x00FENCE(\d+)\x00")
_FENCE_STORE: dict[int, str] = {}
_fence_ids = itertools.count()


def _mask_code_fences(text: str) -> str:
    def _stash(m: Match) -> str:
        i = next(_fence_ids)
        _FENCE_STORE[i] = m.group(0)
        return f"\x00FENCE{i}\x00"

    return _FENCED_CODE_RE.sub(_stash, text)


def _restore_code_fences(text: str) -> str:
    # Fence tokens get rejoined into bucket text alongside surrounding prose
    # (e.g. "...in api/main.py. \x00FENCE0\x00"), landing mid-line. Padding with
    # blank lines puts the restored ``` back at the start of a line, which
    # Python-Markdown's fenced_code extension requires to recognize a block —
    # without it, the fence renders as flat, unhighlighted paragraph text.
    return _FENCE_TOKEN_RE.sub(lambda m: "\n\n" + _FENCE_STORE.pop(int(m.group(1)), "") + "\n\n", text)


_BEFORE_AFTER_HEADING_LINE_RE = re.compile(r"^#{1,6}\s*(BEFORE|AFTER)\s*:?\s*(.*)$", re.IGNORECASE)


def _normalize_before_after_headings(text: str) -> str:
    """Demote stray `# BEFORE: <code>` / `# AFTER:` ATX headings to a bold
    label + fenced code block.

    Some experts label remediation snippets with a Markdown heading instead of
    fencing them (no fence for `_mask_code_fences` to protect), so the code
    renders at the browser's default heading size instead of as code. Run
    AFTER fence-masking so real fenced code is untouched.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    out = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        lines = para.splitlines()
        m = _BEFORE_AFTER_HEADING_LINE_RE.match(lines[0]) if lines else None
        if not m:
            out.append(para)
            i += 1
            continue

        label = m.group(1).upper()
        code_lines = [m.group(2).strip()] if m.group(2).strip() else []
        code_lines.extend(lines[1:])

        # No inline code on the heading line itself — the snippet is likely
        # the very next paragraph (unless that's another label/heading).
        if not code_lines and i + 1 < len(paragraphs):
            nxt = paragraphs[i + 1]
            if nxt.strip() and not nxt.lstrip().startswith(("#", "**")):
                code_lines = nxt.splitlines()
                i += 1

        code = "\n".join(code_lines).strip()
        out.append(f"**{label}:**\n\n```python\n{code}\n```" if code else f"**{label}:**")
        i += 1

    return "\n\n".join(out)


_ORPHAN_LANG_TAG_RE = re.compile(
    r"(?P<pre>.*?)\b(?P<lang>python|json|yaml|yml|javascript|typescript|jsx|tsx|bash|sh|shell|html|css|sql)"
    r"[ \t]*\n(?P<rest>.+)",
    re.IGNORECASE | re.DOTALL,
)
# Guard against wrapping ordinary prose that happens to mention a language by
# name (e.g. "written in Python") — only fence text that actually looks like
# code.
_CODE_LIKE_RE = re.compile(
    r"[(){};=]|^\s*(?:def|class|import|from|const|let|var|function|select|@\w)", re.IGNORECASE | re.MULTILINE
)
# A lone-line file reference right after the dropped fence, e.g.
# "# path/to/file.py:12" (bare — Markdown would otherwise render this as an
# H1) or "`path/to/file.py:12`" (backtick-wrapped). Either way it's a label
# for the snippet, not code, and the "#" form must never reach the Markdown
# renderer un-fenced or it becomes a literal heading.
_FILE_REF_LINE_RE = re.compile(
    r"^[ \t]*(?:"
    r"#{1,6}[ \t]*(?P<hash_ref>[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|java|json|yml|yaml|toml|md|sh|tf|html|css)(?::\d+(?:-\d+)?)?)"
    r"|`(?P<tick_ref>[^`\n]+)`"
    r")[ \t]*$"
)


def _fence_orphaned_code(text: str) -> str:
    """Wrap code that follows a bare, un-fenced language tag (e.g. "...status. python")
    in a proper fenced code block so it renders as code instead of prose.

    Some experts drop the triple-backtick fence entirely and leave only the
    language word behind (as if a "```python" fence lost its backticks), so
    the snippet that follows renders as an ordinary paragraph — and a bare
    "# path/to/file.py:12" reference line right after it renders as a literal
    heading instead of a label.
    """
    m = _ORPHAN_LANG_TAG_RE.search(text)
    if not m:
        return text

    lang = m.group("lang").lower()
    lines = m.group("rest").split("\n")

    while lines and not lines[0].strip():
        lines.pop(0)

    ref_line = ""
    if lines:
        fm = _FILE_REF_LINE_RE.match(lines[0])
        if fm:
            ref_line = (fm.group("hash_ref") or fm.group("tick_ref") or "").strip()
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)

    code = "\n".join(lines).strip()
    if not code or not _CODE_LIKE_RE.search(code):
        return text

    fenced = f"```{lang}\n{code}\n```"
    prefix = f"`{ref_line}`\n\n" if ref_line else ""
    return m.group("pre").rstrip() + "\n\n" + prefix + fenced


def _md_render(text: str) -> str:
    """Restore masked fences, then render markdown to HTML."""
    return _md.markdown(
        _restore_code_fences(text),
        extensions=["fenced_code", "tables", "sane_lists"],
    )


# --- Findings Card Configuration (Markdown-first) ---

_FINDING_HEADER_MD_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*)?(\d+)\.\s*(?:\*\*)?\s*\[?(CRITICAL|HIGH|MEDIUM|LOW|INFO)\]?\s*(?:\*\*)?[:\-–]?\s*([^<\n]+?)(?:\*\*)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_FINDING_LABEL_MD_RE = re.compile(
    r"^\s*(?:-\s*)?\*\*(Confluence Rule|Rule|Standard|Observation|Evidence|"
    r"Violation|Issue|Problem|Threat|Required Action|Recommendation|Remediation|"
    r"Fix|Mitigation|Defense in Depth|Why better|Caveat|Caveats|Impact|Severity|Location)"
    r"\*\*\s*[:：]?\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)

_LABEL_BUCKETS = {
    "rule": {"confluence rule", "rule", "standard"},
    "obs": {"observation", "evidence", "location"},
    "viol": {"violation", "issue", "problem", "threat", "impact", "severity"},
    "action": {
        "required action",
        "recommendation",
        "remediation",
        "fix",
        "mitigation",
        "defense in depth",
        "why better",
        "caveat",
        "caveats",
    },
}

_BUCKET_META = {
    "rule": ("menu_book", "Rule", "#004B8D", "#f0f7ff"),
    "obs": ("visibility", "Observation", "#002C77", "#f8fafc"),
    "viol": ("error", "Violation", "#ba1a1a", "#fef2f2"),
    "action": ("bolt", "Required Action", "#004B8D", "#f0f7ff"),
}

# bg, text, border, box-shadow-css, dot-color
_SEVERITY_STYLE = {
    "CRITICAL": ("transparent", "#dc2626", "transparent", "none", "#dc2626"),
    "HIGH": ("transparent", "#ea580c", "transparent", "none", "#ea580c"),
    "MEDIUM": ("transparent", "#d97706", "transparent", "none", "#d97706"),
    "LOW": ("transparent", "#16a34a", "transparent", "none", "#16a34a"),
    "INFO": ("transparent", "#0054a6", "transparent", "none", "#0054a6"),
}


_SEVERITY_ICON = {
    "CRITICAL": "emergency",
    "HIGH": "warning",
    "MEDIUM": "priority_high",
    "LOW": "check_circle",
    "INFO": "info",
}


def render_status_pill(label: str, color: str, icon: str = "info", *, size: str = "11px") -> str:
    """Solid, high-contrast status/severity pill: colored background, white text, icon.

    Severity needs to be scannable at a glance, not just inferred from a thin
    border or a colored word — a filled pill reads instantly even skimming fast.
    """
    return (
        f'<span class="status-pill" style="display:inline-flex;align-items:center;gap:5px;'
        f"background:{color};color:#fff;font-weight:800;font-size:{size};letter-spacing:0.04em;"
        f'text-transform:uppercase;padding:4px 12px;border-radius:999px;line-height:1.4;">'
        f'<span class="material-symbols-outlined" style="font-size:14px;font-variation-settings:\'FILL\' 1;">{icon}</span>'
        f"{label}</span>"
    )


def render_severity_badge(severity: str, *, size: str = "11px") -> str:
    """Solid severity pill (CRITICAL/HIGH/MEDIUM/LOW/INFO) using the shared severity palette."""
    sev_key = severity.upper()
    _, fg, _, _, _ = _SEVERITY_STYLE.get(sev_key, _SEVERITY_STYLE["INFO"])
    icon = _SEVERITY_ICON.get(sev_key, "info")
    return render_status_pill(sev_key, fg, icon, size=size)


def _get_status_chip_html(severity: str) -> str:
    """Generate HTML for the redesigned status chip with a leading dot."""
    sev = severity.upper()
    klass = "info"
    color = "#0054a6"
    if sev in ("CRITICAL", "HIGH", "FAIL", "REJECTED"):
        klass = "fail"
        color = "#dc2626"
    elif sev in ("MEDIUM", "WARN", "WARNING"):
        klass = "warn"
        color = "#d97706"
    elif sev in ("LOW", "PASS", "SUCCESS", "APPROVED", "CERTIFIED"):
        klass = "pass"
        color = "#16a34a"

    return (
        f'<span class="status-chip status-chip-{klass}" style="display:inline-flex;align-items:center;gap:4px;color:{color};font-weight:700;font-size:11px;text-transform:uppercase;">'
        f'<span class="status-chip-dot" style="background:{color};width:6px;height:6px;border-radius:50%;display:inline-block;animation:pulse-dot 1.8s ease-in-out infinite;"></span>'
        f"{sev}</span>"
    )


# --- Governance Configuration ---

_GOV_RULE_HEADER_RE = re.compile(
    r"^\s*(?:(\d+)\.\s+)?\*{0,2}"
    # Rule ID codes (GOV-01, SEC-12, ...) are matched case-SENSITIVELY via the
    # scoped (?-i:) group — with IGNORECASE, ordinary lowercase words followed
    # by a dash ("google-adk", "status-...") would parse as rule headers.
    r"(?P<ids>(?-i:[A-Z][A-Z0-9]{1,5}(?:-\d{2,3})?(?:\s*[/&]\s*[A-Z][A-Z0-9]{1,5}(?:-\d{2,3})?)*)|Architecture Standard Violation|Standard Violation)"
    r"\s*[:│\|\-–—]\s*"
    r"(?P<title>[^\n*│\|]+?)\*{0,2}"
    r"(?:\s*[│\|]\s*(?P<status>[✅❌⚠️🟢🔴🟡✓✗]?\s*(?:PASS|FAIL|WARN|REJECT(?:ED)?|APPROV(?:ED)?|COMPLIANT|NON[- ]COMPLIANT)(?:\s*\([+−\-]?\d+\))?))?"
    r"\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_GOV_TIER_RE = re.compile(
    r"^\s*##+\s*(?:🚨|🛡️|🛡|⚠️|⚠|✅)?\s*(Tier\s*\d[^\n]*?)$",
    re.MULTILINE | re.IGNORECASE,
)

_GOV_LABEL_RE = re.compile(
    r"^\s*\*?\*?(Rule(?: Verbatim)?|Standard|Finding|Audit Finding|Observation|Evidence|Impact|Severity|"
    r"Penalty|Remediation|Required Action|Recommendation|Status|Result|Verdict)\*?\*?\s*[:：]\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

_GOV_STATUS_LINE_RE = re.compile(
    r"^\s*\*?\*?(Role|Auditor|Date of Audit|Codebase Target|Audit Status|Final Decision|"
    r"Final Score|Audit Score|Status|Score|Verdict|Total Score)\*?\*?\s*[:：]\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_GOV_LABEL_BUCKET = {
    "rule": ("menu_book", "Rule"),
    "rule verbatim": ("menu_book", "Rule"),
    "standard": ("menu_book", "Standard"),
    "finding": ("fact_check", "Finding"),
    "audit finding": ("fact_check", "Finding"),
    "observation": ("fact_check", "Observation"),
    "evidence": ("fact_check", "Evidence"),
    "impact": ("warning", "Impact"),
    "severity": ("warning", "Severity"),
    "penalty": ("remove_circle", "Penalty"),
    "remediation": ("bolt", "Remediation"),
    "required action": ("bolt", "Required Action"),
    "recommendation": ("bolt", "Recommendation"),
    "status": ("flag", "Status"),
    "result": ("flag", "Result"),
    "verdict": ("flag", "Verdict"),
}

# --- Shared Utility Functions ---


def _highlight_inline_evidence(text: str) -> str:
    """Wrap file:line references in <code>, skipping content inside HTML tags."""

    def _replacer(m: re.Match) -> str:
        before = text[: m.start()]
        # Skip if inside an HTML tag (more unclosed < than > before this match)
        if before.count("<") > before.count(">"):
            return m.group(0)
        # Skip if already inside a <code> element (e.g. a markdown backtick span
        # like `.well-known/agent.json`) — otherwise this nests <code><code>...
        if before.count("<code") > before.count("</code>"):
            return m.group(0)
        return (
            f'<code class="ev-file">{m.group(1)}'
            + (f':<span class="ev-line">{m.group(2)}</span>' if m.group(2) else "")
            + "</code>"
        )

    return re.sub(
        r"\b([A-Za-z0-9_./\\-]+\.(?:py|ts|js|go|java|json|yml|yaml|toml|md|sh|tf|html|css))(?::(\d+))?\b",
        _replacer,
        text,
    )


def _bucket_for_label(label: str) -> str | None:
    label = label.strip().lower()
    for bucket, names in _LABEL_BUCKETS.items():
        if label in names:
            return bucket
    return None


# --- Findings Structurization (Markdown-based) ---


def _render_finding_card_md(num: str, severity: str, title: str, body: str) -> str:
    sev_key = severity.upper()

    label_matches = list(_FINDING_LABEL_MD_RE.finditer(body))

    leftover_md = ""
    rows = {"rule": [], "obs": [], "viol": [], "action": []}

    if not label_matches:
        leftover_md = body
    else:
        if label_matches[0].start() > 0:
            leftover_md = body[: label_matches[0].start()].strip()

        for i, lm in enumerate(label_matches):
            label = lm.group(1)
            bucket = _bucket_for_label(label)

            content_start = lm.end()
            content_end = label_matches[i + 1].start() if i + 1 < len(label_matches) else len(body)

            val_first_line = lm.group(2).strip()
            val_rest = body[content_start:content_end].strip()
            val = val_first_line
            if val_rest:
                val = val + "\n" + val_rest

            if bucket:
                rows[bucket].append((label, val.strip()))
            else:
                rows["obs"].append((label, val.strip()))

    row_html_parts = []
    for bucket in ("rule", "obs", "viol", "action"):
        if not rows[bucket]:
            continue
        icon, label_text, color, bg_color = _BUCKET_META[bucket]

        bucket_md = "\n\n".join(f"**{lbl}:** {val}" if len(rows[bucket]) > 1 else val for lbl, val in rows[bucket])
        bucket_md = _fence_orphaned_code(bucket_md)
        body_html = _md_render(bucket_md)
        body_html = _highlight_inline_evidence(body_html)

        row_html_parts.append(
            f'<div class="finding-row-card" style="background:{bg_color};border-left:3px solid {color};">'
            f'  <div class="finding-row-label" style="color:{color};">'
            f'    <span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle;">{icon}</span>'
            f"    <span>{label_text}</span>"
            f"  </div>"
            f'  <div class="finding-row-body prose prose-slate prose-sm max-w-none">{body_html}</div>'
            f"</div>"
        )

    rows_html = "".join(row_html_parts)
    leftover_section = ""
    if leftover_md:
        leftover_html = _md_render(_fence_orphaned_code(leftover_md))
        leftover_html = _highlight_inline_evidence(leftover_html)
        leftover_section = (
            f'<div class="finding-leftover prose prose-slate prose-sm max-w-none mb-4">{leftover_html}</div>'
        )

    return (
        f'<div class="finding-card-v2 sev-card-{sev_key.lower()}" id="finding-{num}" data-severity="{sev_key}">'
        f'  <div class="finding-card-head">'
        f'    <span class="finding-num">#{num}</span>'
        f"    {render_severity_badge(sev_key)}"
        f'    <span class="finding-title">{_restore_code_fences(title).strip()}</span>'
        f"  </div>"
        f'  <div class="finding-card-body">{leftover_section}{rows_html}</div>'
        f"</div>"
    )


def structurize_findings_html(md_text: str) -> str:
    """Structurize findings from a Markdown string into styled HTML cards."""
    if not md_text or not md_text.strip():
        return ""

    # Mask code fences FIRST so no segmentation regex can match inside them.
    md_text = _mask_code_fences(md_text)
    md_text = _normalize_before_after_headings(md_text)

    matches = list(_FINDING_HEADER_MD_RE.finditer(md_text))
    if not matches:
        # Fallback: if no headers found, just render the whole thing as markdown
        return f'<div class="findings-style-scope"><div class="prose prose-slate prose-sm max-w-none">{_md_render(md_text)}</div></div>'

    out_parts = ['<div class="findings-style-scope">']

    if matches[0].start() > 0:
        preamble = md_text[: matches[0].start()].strip()
        if preamble:
            out_parts.append(f'<div class="prose prose-slate prose-sm max-w-none mb-6">{_md_render(preamble)}</div>')

    tally = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    cards_html = []

    for i, m in enumerate(matches):
        num = m.group(1)
        severity = m.group(2).upper()
        title = m.group(3).strip().lstrip(":–-").strip()

        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        body = md_text[body_start:body_end].strip()

        tally[severity] = tally.get(severity, 0) + 1
        cards_html.append(_render_finding_card_md(num, severity, title, body))

    chip_strip = ['<div class="findings-tally" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;">']
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        if tally.get(sev, 0) == 0:
            continue
        _, fg, _, _, _ = _SEVERITY_STYLE[sev]
        chip_strip.append(render_status_pill(f"{sev} {tally[sev]}", fg, _SEVERITY_ICON.get(sev, "info")))
    chip_strip.append("</div>")
    out_parts.append("".join(chip_strip))
    out_parts.extend(cards_html)
    out_parts.append("</div>")

    return "".join(out_parts)


# --- Governance Structurization ---


def _gov_status_chip(label: str, value: str) -> str:
    val_lower = value.lower()
    color = "#475569"  # Default role color
    icon = "info"
    is_status_word = False
    if "reject" in val_lower or "fail" in val_lower or "non-compliant" in val_lower:
        color, icon, is_status_word = "#dc2626", "cancel", True
    elif "approv" in val_lower or "pass" in val_lower or "compliant" in val_lower:
        color, icon, is_status_word = "#16a34a", "verified", True
    elif "warn" in val_lower or "partial" in val_lower or "review" in val_lower:
        color, icon, is_status_word = "#d97706", "warning", True
    elif label.lower() in ("final score", "score", "total score"):
        color = "#0054a6"
    value_clean = re.sub(r"^[^\w]*", "", value).strip()
    if is_status_word:
        return (
            f'<span class="gov-status-chip" style="display:inline-flex;align-items:center;gap:8px;margin-right:16px;font-size:13px;">'
            f'<strong style="color:#334155;">{label}:</strong>{render_status_pill(value_clean.upper(), color, icon, size="12px")}</span>'
        )
    return f'<span class="gov-status-chip" style="color:{color};font-weight:700;display:inline-flex;align-items:center;margin-right:16px;font-size:13px;background:transparent;border:none;padding:0;"><strong>{label}:</strong>&nbsp;{value_clean}</span>'


def _md_inline(text: str) -> str:
    """Helper to render markdown without surrounding paragraph tags."""
    rendered = _md.markdown(_restore_code_fences(text.strip()), extensions=["fenced_code", "tables"]).strip()
    if rendered.startswith("<p>") and rendered.endswith("</p>"):
        rendered = rendered[3:-4]
    return rendered


def _classify_status(status_text: str, body_text: str) -> tuple[str, str]:
    st = (status_text or "").lower()
    if any(
        k in st
        for k in (
            "fail",
            "reject",
            "non-compliant",
            "non compliant",
            "\u274c",
            "\ud83d\udd34",
        )
    ):
        return "fail", "Fail"
    if any(k in st for k in ("warn", "\u26a0", "\ud83d\udfe1")):
        return "warn", "Warn"
    if any(k in st for k in ("pass", "approv", "compliant", "\u2705", "\ud83d\udfe2")):
        return "pass", "Pass"
    body_lower = (body_text or "").lower()
    verdict_match = re.search(r"\*?\*?verdict\*?\*?\s*[:\uff1a]\s*([^\n]+)", body_lower)
    if verdict_match:
        v = verdict_match.group(1)
        if any(k in v for k in ("\u274c", "fail", "reject", "non-compliant")):
            return "fail", "Fail"
        if any(k in v for k in ("\u26a0", "warn", "partial")):
            return "warn", "Warn"
        if any(k in v for k in ("\u2705", "pass", "compliant", "approv")):
            return "pass", "Pass"
    if any(k in body_lower for k in ("critical violation", "hard gate fail", "rejected")):
        return "fail", "Fail"
    return "", ""


def _parse_rule_body(body: str) -> dict:
    fields: dict[str, list[str]] = {}
    leftover_lines: list[str] = []
    normalized = re.sub(
        r"(?<!^)(\*?\*?(?:Rule|Standard|Finding|Audit Finding|Observation|Evidence|Impact|Severity|Penalty|Remediation|Required Action|Recommendation|Status|Result|Verdict)\*?\*?\s*[:\uff1a])",
        r"\n\1",
        body,
        flags=re.IGNORECASE,
    )
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _GOV_LABEL_RE.match(stripped)
        if m:
            lbl = m.group(1).strip().lower()
            val = m.group(2).strip()
            meta = _GOV_LABEL_BUCKET.get(lbl)
            if meta:
                _icon, display = meta
                fields.setdefault(display, []).append(val)
                continue
        leftover_lines.append(line)

    joined = {k: "<br><br>".join(_md_inline(v) for v in vals) for k, vals in fields.items()}
    leftover = "\n".join(leftover_lines).strip()
    if leftover:
        joined["__leftover__"] = leftover
    return joined


def _extract_penalty(status_text: str, body_text: str, tier_penalty: str = "") -> str:
    for src in (status_text or "", body_text or ""):
        m = re.search(r"\(([+\u2212\-]?\d+)\s*(?:points?|pts?)?\)", src)
        if m:
            return m.group(1)
        m = re.search(r"penalty[:\s]*[+\u2212\-]?(\d+)\s*(?:points?|pts?)?", src, re.IGNORECASE)
        if m:
            return f"-{m.group(1)}"
    klass, _ = _classify_status(status_text, body_text)
    if tier_penalty and klass == "fail":
        return tier_penalty
    return ""


def _render_rule_row(rule: dict) -> str:
    klass, label = _classify_status(rule["status"], rule["body"])

    # Map internal classification to the finding-card-v2 severity buckets
    sev_map = {"fail": "CRITICAL", "warn": "MEDIUM", "pass": "INFO"}
    severity = sev_map.get(klass, "INFO")
    _, fg, _, _, _ = _SEVERITY_STYLE.get(severity, _SEVERITY_STYLE["INFO"])

    penalty = _extract_penalty(rule["status"], rule["body"], rule.get("tier_penalty", ""))
    penalty_html = (
        f'<span class="gov-score-impact" style="margin-left:auto; font-size:11px; font-weight:900;">{penalty}</span>'
        if penalty
        else ""
    )

    _verdict_icon = {"Fail": "cancel", "Warn": "warning", "Pass": "check_circle"}
    verdict_label = label.upper() if label else "INFO"
    verdict_pill = render_status_pill(verdict_label, fg, _verdict_icon.get(label, "info"))

    fields = _parse_rule_body(rule["body"])
    row_html_parts = []

    # Map governance fields to finding-card-v2 row buckets
    field_mappings = [
        ("Rule", ["Rule", "Standard"], "rule"),
        ("Observation", ["Finding", "Observation", "Evidence"], "obs"),
        ("Violation", ["Impact", "Severity", "Penalty"], "viol"),
        (
            "Required Action",
            ["Required Action", "Remediation", "Recommendation"],
            "action",
        ),
    ]

    for display_label, source_keys, bucket in field_mappings:
        val = None
        for k in source_keys:
            if k in fields:
                val = fields[k]
                break

        if val:
            icon, bucket_label, color, bg_color = _BUCKET_META[bucket]
            row_html_parts.append(
                f'<div class="finding-row-card" style="background:{bg_color};border-left:3px solid {color};">'
                f'  <div class="finding-row-label" style="color:{color};">'
                f'    <span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle;">{icon}</span>'
                f"    <span>{display_label}</span>"
                f"  </div>"
                f'  <div class="finding-row-body prose prose-slate prose-sm max-w-none">{val}</div>'
                f"</div>"
            )

    if not row_html_parts:
        leftover = fields.get("__leftover__", "").strip()
        if leftover:
            leftover_html = _highlight_inline_evidence(_md_render(leftover))
            row_html_parts.append(
                f'<div class="finding-leftover prose prose-slate prose-sm max-w-none mb-4">{leftover_html}</div>'
            )

    return (
        f'<div class="finding-card-v2 sev-card-{severity.lower()}">'
        f'  <div class="finding-card-head" style="display:flex; align-items:center;">'
        f'    <span class="finding-num">{rule["ids"]}</span>'
        f"    {verdict_pill}"
        f'    <span class="finding-title">{rule["title"]}</span>'
        f"    {penalty_html}"
        f"  </div>"
        f'  <div class="finding-card-body">{"".join(row_html_parts)}</div>'
        f"</div>"
    )


def _render_tier_table(tier_text: str, tier_class: str, rules: list) -> str:
    pass_n = sum(1 for r in rules if _classify_status(r["status"], r["body"])[0] == "pass")
    fail_n = sum(1 for r in rules if _classify_status(r["status"], r["body"])[0] == "fail")
    warn_n = sum(1 for r in rules if _classify_status(r["status"], r["body"])[0] == "warn")

    tally = (
        f'<div class="gov-tier-tally">'
        f'  <span class="gov-tally-pass">Pass {pass_n}</span>'
        f'  <span class="gov-tally-warn">Warn {warn_n}</span>'
        f'  <span class="gov-tally-fail">Fail {fail_n}</span>'
        f"</div>"
    )

    rules_html = (
        "".join(_render_rule_row(r) for r in rules) if rules else '<div class="gov-empty">No rules in this tier.</div>'
    )

    return (
        f'<div class="gov-tier-container gov-tier-{tier_class} reveal-on-scroll">'
        f'  <div class="gov-tier-header">'
        f'    <div class="gov-tier-title-wrap">'
        f'      <span class="material-symbols-outlined">layers</span>'
        f'      <span class="gov-tier-name">{tier_text}</span>'
        f"    </div>"
        f"    {tally}"
        f"  </div>"
        f'  <div class="gov-tier-body">{rules_html}</div>'
        f"</div>"
    )


def _gov_classify_severity(text: str) -> str:
    """Map governance status keywords/emoji to a finding severity bucket."""
    t = text.lower()
    if any(
        k in t
        for k in (
            "\u274c",
            "fail",
            "reject",
            "non-compliant",
            "non compliant",
            "critical",
            "violation",
            "violated",
        )
    ):
        return "CRITICAL"
    if any(k in t for k in ("\u26a0", "\ud83d\udfe1", "warn", "partial", "deprecated")):
        return "MEDIUM"
    if any(
        k in t
        for k in (
            "\u2705",
            "\ud83d\udfe2",
            "pass",
            "compliant",
            "approv",
            "verified",
            "ok",
        )
    ):
        return "INFO"
    return "INFO"


# Item boundary patterns for freeform governance content:
#   ❌/✅/⚠️ Item N: title    OR    ❌ Some Title
#   **Bold Heading (...)**:   (scanner-style headings)
#   ### N. Title              (markdown sub-headers)
_GOV_ITEM_BOUNDARY_RE = re.compile(
    r"^\s*(?:"
    r"(?P<emoji>[\u274c\u2705\u26a0\ud83d\udfe2\ud83d\udd34\ud83d\udfe1])\s*(?P<etitle>(?:Item\s*\d+\s*[:\-\u2013]\s*)?[^\n]+?)"
    r"|\*\*(?P<btitle>[A-Z][^*\n]{2,160}?)\*\*\s*[:\uff1a]?\s*$"
    r"|#{2,4}\s+(?P<htitle>\d+\.\s+[^\n]+|[A-Z][^\n]{2,160}?)"
    r")\s*$",
    re.MULTILINE,
)

_GOV_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:#{1,3}\s+)?(?P<num>\d+)\.\s+(?P<title>[A-Z][A-Z0-9 \-/&\(\)]{4,120})\s*$",
    re.MULTILINE,
)


def _render_gov_freeform_card(num: int, severity: str, title: str, body: str) -> str:
    """Render a governance item as a finding-card-v2 styled card."""
    sev_key = severity.upper()

    # Reuse finding-label parser: detect Violation, Required Action, Result, Observation, etc.
    label_matches = list(_FINDING_LABEL_MD_RE.finditer(body))
    rows = {"rule": [], "obs": [], "viol": [], "action": []}
    leftover_md = ""

    if not label_matches:
        leftover_md = body.strip()
    else:
        if label_matches[0].start() > 0:
            leftover_md = body[: label_matches[0].start()].strip()
        for i, lm in enumerate(label_matches):
            label = lm.group(1)
            bucket = _bucket_for_label(label) or "obs"
            content_start = lm.end()
            content_end = label_matches[i + 1].start() if i + 1 < len(label_matches) else len(body)
            val = (lm.group(2).strip() + "\n" + body[content_start:content_end].strip()).strip()
            rows[bucket].append((label, val))

    # Also handle scanner-style "*Result:* ..." italic labels by promoting to obs/viol.
    italic_result_re = re.compile(r"\*\s*(Result|Status|Verdict)\s*[:\uff1a]?\s*\*\s*([^\n]+)", re.IGNORECASE)
    for m in italic_result_re.finditer(leftover_md):
        rows["viol" if "fail" in m.group(2).lower() or "reject" in m.group(2).lower() else "obs"].append(
            (m.group(1), m.group(2).strip())
        )
    leftover_md = italic_result_re.sub("", leftover_md).strip()

    row_html_parts = []
    for bucket in ("rule", "obs", "viol", "action"):
        if not rows[bucket]:
            continue
        icon, label_text, color, bg_color = _BUCKET_META[bucket]
        bucket_md = "\n\n".join(f"**{lbl}:** {val}" if len(rows[bucket]) > 1 else val for lbl, val in rows[bucket])
        body_html = _highlight_inline_evidence(_md_render(_fence_orphaned_code(bucket_md)))
        row_html_parts.append(
            f'<div class="finding-row-card" style="background:{bg_color};border-left:3px solid {color};">'
            f'  <div class="finding-row-label" style="color:{color};">'
            f'    <span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle;">{icon}</span>'
            f"    <span>{label_text}</span>"
            f"  </div>"
            f'  <div class="finding-row-body prose prose-slate prose-sm max-w-none">{body_html}</div>'
            f"</div>"
        )

    leftover_section = ""
    if leftover_md:
        leftover_html = _highlight_inline_evidence(_md_render(_fence_orphaned_code(leftover_md)))
        leftover_section = (
            f'<div class="finding-leftover prose prose-slate prose-sm max-w-none mb-4">{leftover_html}</div>'
        )

    return (
        f'<div class="finding-card-v2 sev-card-{severity.lower()}">'
        f'  <div class="finding-card-head">'
        f'    <span class="finding-num">G{num:02d}</span>'
        f"    {render_severity_badge(sev_key)}"
        f'    <span class="finding-title">{_restore_code_fences(title).strip()}</span>'
        f"  </div>"
        f'  <div class="finding-card-body">{leftover_section}{"".join(row_html_parts)}</div>'
        f"</div>"
    )


def _structurize_gov_freeform(md_text: str) -> str:
    """Render free-form governance markdown as findings-style cards grouped by section."""
    out = ['<div class="gov-scope findings-style-scope">']

    # 1. Extract status chips from the whole doc (e.g. **Verdict:** REJECTED).
    status_chips = []
    chip_lines = set()
    for m in _GOV_STATUS_LINE_RE.finditer(md_text):
        status_chips.append(_gov_status_chip(m.group(1), m.group(2)))
        chip_lines.add(m.group(0).strip())
    if status_chips:
        out.append('<div class="gov-status-row">' + "".join(status_chips) + "</div>")

    # 2. Find top-level numbered section headers; each becomes a tier group.
    sections = list(_GOV_SECTION_HEADER_RE.finditer(md_text))

    if not sections:
        # No sections found – treat the whole document as one group.
        sections_iter = [(0, len(md_text), "Audit Findings")]
    else:
        # Render any pre-section preamble as plain prose first.
        if sections[0].start() > 0:
            preamble = md_text[: sections[0].start()].strip()
            preamble_lines = [ln for ln in preamble.splitlines() if ln.strip() not in chip_lines]
            preamble = "\n".join(preamble_lines).strip()
            if preamble:
                out.append(
                    f'<div class="gov-preamble prose prose-slate prose-sm max-w-none mb-8">{_md_render(preamble)}</div>'
                )
        sections_iter = []
        for i, sm in enumerate(sections):
            s_end = sections[i + 1].start() if i + 1 < len(sections) else len(md_text)
            sections_iter.append((sm.start(), s_end, f"{sm.group('num')}. {sm.group('title').strip()}"))

    card_idx = 0
    for s_start, s_end, section_title in sections_iter:
        # Skip the section header line itself when extracting body.
        body_start = md_text.find("\n", s_start) + 1 if md_text.find("\n", s_start) != -1 else s_start
        section_body = md_text[body_start:s_end].strip()

        # Find item boundaries inside this section.
        items = list(_GOV_ITEM_BOUNDARY_RE.finditer(section_body))

        # Tier-style header for the section (reuse governance tier styling).
        tier_class = (
            "tier3"
            if "violation" in section_title.lower() or "hard gate" in section_title.lower()
            else "tier2"
            if "checklist" in section_title.lower()
            else "tier1"
        )
        out.append(
            f'<div class="gov-tier-container gov-tier-{tier_class} reveal-on-scroll">'
            f'  <div class="gov-tier-header">'
            f'    <div class="gov-tier-title-wrap">'
            f'      <span class="material-symbols-outlined">layers</span>'
            f'      <span class="gov-tier-name">{section_title}</span>'
            f"    </div>"
            f"  </div>"
            f'  <div class="gov-tier-body" style="gap:0;">'
        )

        if not items:
            # Render the section body as a single info card.
            card_idx += 1
            out.append(_render_gov_freeform_card(card_idx, "INFO", section_title, section_body))
        else:
            # Pre-item content (intro paragraph) rendered as prose.
            if items[0].start() > 0:
                intro = section_body[: items[0].start()].strip()
                if intro:
                    out.append(f'<div class="prose prose-slate prose-sm max-w-none mb-4">{_md_render(intro)}</div>')
            for i, im in enumerate(items):
                item_end = items[i + 1].start() if i + 1 < len(items) else len(section_body)
                title_raw = (im.group("etitle") or im.group("btitle") or im.group("htitle") or "").strip()
                emoji = im.group("emoji") or ""
                body = section_body[im.end() : item_end].strip()
                severity = _gov_classify_severity(emoji + " " + title_raw + " " + body[:200])
                card_idx += 1
                out.append(_render_gov_freeform_card(card_idx, severity, title_raw, body))

        out.append("</div></div>")

    out.append("</div>")
    return "".join(out)


def structurize_governance_md(md_text: str) -> str:
    if not md_text or not md_text.strip():
        return ""

    # Mask code fences FIRST so no segmentation regex can match inside them
    # (_structurize_gov_freeform receives the already-masked text).
    md_text = _mask_code_fences(md_text)
    md_text = _normalize_before_after_headings(md_text)

    rule_matches = list(_GOV_RULE_HEADER_RE.finditer(md_text))
    if not rule_matches:
        # Free-form governance content (the common case): render as findings-style cards.
        return _structurize_gov_freeform(md_text)

    out = ['<div class="gov-scope">']

    all_tier_positions = [(m.start(), m.end(), m.group(1)) for m in _GOV_TIER_RE.finditer(md_text)]
    tier_line_spans = [(s, e) for s, e, _ in all_tier_positions]

    header_end = rule_matches[0].start()

    if not all_tier_positions:
        header_chunk = md_text[:header_end]
    else:
        sorted_spans = sorted(tier_line_spans)
        header_parts = []
        last_idx = 0
        for s, e in sorted_spans:
            if s >= header_end:
                break
            if s > last_idx:
                header_parts.append(md_text[last_idx:s])
            last_idx = min(e, header_end)
        if last_idx < header_end:
            header_parts.append(md_text[last_idx:header_end])
        header_chunk = "".join(header_parts)

    status_chips = []
    remaining_lines = []
    for line in header_chunk.splitlines():
        m = _GOV_STATUS_LINE_RE.match(line)
        if m:
            status_chips.append(_gov_status_chip(m.group(1), m.group(2)))
        else:
            remaining_lines.append(line)

    if status_chips:
        out.append('<div class="gov-status-row">' + "".join(status_chips) + "</div>")

    leftover_md = "\n".join(remaining_lines).strip()
    if leftover_md:
        out.append(_md_render(leftover_md))

    events = []
    for m in _GOV_RULE_HEADER_RE.finditer(md_text):
        if m.start() >= rule_matches[0].start():
            events.append(("rule", m.start(), m))
    for s, _e, tier_text in all_tier_positions:
        events.append(("tier", s, tier_text))
    events.sort(key=lambda e: e[1])

    tiers = []
    current_tier = None
    if not (all_tier_positions and events and events[0][0] == "tier") and events:
        current_tier = {"text": "Governance Rules", "class": "tier1", "rules": []}
        tiers.append(current_tier)

    for i, evt in enumerate(events):
        next_start = events[i + 1][1] if i + 1 < len(events) else len(md_text)
        if evt[0] == "tier":
            tier_text = evt[2]
            tier_class = (
                "tier2" if "tier 2" in tier_text.lower() else "tier3" if "tier 3" in tier_text.lower() else "tier1"
            )
            pm = re.search(
                r"penalty[:\s]*[+\u2212\-]?(\d+)\s*(?:points?|pts?)",
                md_text[evt[1] : next_start],
                re.IGNORECASE,
            )
            current_tier = {
                "text": tier_text,
                "class": tier_class,
                "rules": [],
                "penalty": f"-{pm.group(1)}" if pm else "",
            }
            tiers.append(current_tier)
        else:
            m = evt[2]
            header_line_end = md_text.find("\n", m.end())
            rule_body = md_text[header_line_end + 1 if header_line_end != -1 else m.end() : next_start]
            if current_tier is None:
                current_tier = {
                    "text": "Governance Rules",
                    "class": "tier1",
                    "rules": [],
                    "penalty": "",
                }
                tiers.append(current_tier)
            current_tier["rules"].append(
                {
                    "num": m.group(1) or "",
                    "ids": m.group("ids"),
                    "title": m.group("title").strip().lstrip("|").strip(),
                    "status": (m.group("status") or "").strip(),
                    "body": rule_body,
                    "tier_penalty": current_tier.get("penalty", ""),
                }
            )

    for t in tiers:
        out.append(_render_tier_table(t["text"], t["class"], t["rules"]))
    out.append("</div>")
    return "".join(out)
