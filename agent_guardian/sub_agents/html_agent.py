from __future__ import annotations

"""
HTML Agent — Premium Dashboard Generator.

Role in Pipeline:
Runs after `metrics_agent`. It consumes the synthesized markdown, structured metrics,
and individual expert reviews to render a high-fidelity, styled HTML report.
The report is both saved as an ADK artifact and written to state.

State Interactions:
- Reads: `synthesis_result`, `governance_review_result`, `security_review_result`, `quality_review_result`, `adk_review_result`, `validation_result`, `review_metrics`, `metrics_chart_b64`, `logic_file_count`, `module_map`
- Writes: `html_report_content`, `scorecard_html`, `repo_metadata_html`, `metrics_chart_html`, `expert_reviews_html`, `report_grade`, `overall_score`, `confidence_score`
"""
import os
import re
import logging
import datetime
import base64
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from agent_guardian.config import Config
from agent_guardian.prompts import HTML_REPORT_PROMPT
from ..utils.html_structurizers import (
    structurize_findings_html,
    structurize_governance_md,
    render_status_pill,
    _GOV_RULE_HEADER_RE,
    _GOV_ITEM_BOUNDARY_RE,
    _GOV_SECTION_HEADER_RE,
)
from agent_guardian.utils.token_utils import (
    synthesis_token_manager,
    synthesis_budget_callback,
)
from .registry import EXPERT_REGISTRY, EXPERT_STATE_KEYS

logger = logging.getLogger(__name__)
_cfg = Config()

# --- Configuration & Styling ------------------------------------------------

# Derived from the expert registry (single source of truth) so a new expert
# automatically appears in the report.
_EXPERT_SECTIONS = [(s.state_key, s.display_title, s.icon, s.accent) for s in EXPERT_REGISTRY]

_EXPERT_REVIEW_STYLE = """
<style>
.expert-review-body { color:#1e293b; font-family:system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, sans-serif; font-size:14.5px; line-height:1.7; overflow-wrap: break-word; text-align: left; }
.expert-review-body h1, .expert-review-body h2 { font-size:15px; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; margin:28px 0 14px; padding-bottom:8px; border-bottom:2px solid #e2e8f0; color:#0054a6; text-align: left; }
.expert-review-body h3 { font-size:14px; font-weight:700; margin:20px 0 10px; color:#1e293b; text-align: left; }
.expert-review-body p { margin:0 0 12px; text-align: left; }
.expert-review-body ul, .expert-review-body ol { margin:0 0 16px 20px; padding:0; text-align: left; }
.expert-review-body li { margin:7px 0; text-align: left; }
.expert-review-body strong { color:#0054a6; font-weight:700; }
.expert-review-body code { background:transparent; color:#0054a6; padding:0; font-family:ui-monospace,monospace; font-size:12.5px; font-weight:700; }
.expert-review-body pre { background:#f8fafc; color:#1e293b; padding:16px 20px; border-radius:8px; overflow-x:auto; font-size:13px; margin:14px 0 22px; border:1px solid #e2e8f0; font-family:ui-monospace,monospace; }
.expert-review-body .pill { display:inline-flex; align-items:center; gap:4px; font-size:11px; font-weight:700; text-transform:uppercase; }
.expert-review-body .pill-pass { color:#16a34a; }
.expert-review-body .pill-fail { color:#dc2626; }
.expert-review-body .pill-warn { color:#d97706; }
.expert-review-body .pill-info { color:#0054a6; }
.expert-review-body .finding-row { padding:12px 16px; margin:10px 0; border:1px solid #e2e8f0; background:#f8fafc; }
.expert-review-body .finding-row.fail { border-left:3px solid #dc2626; }
.expert-review-body .finding-row.pass { border-left:3px solid #16a34a; }
.expert-card-details summary::-webkit-details-marker { display:none; }
.expert-card-details[open] .expand-chevron { transform:rotate(180deg); }
.expand-chevron { transition:transform 0.25s ease; display:inline-block; }
</style>
"""

# --- Helper Functions -------------------------------------------------------


def _get_score_badge(score: float) -> str:
    if score >= 90:
        return render_status_pill("GOOD", "#16a34a", "check_circle", size="10px")
    if score >= 70:
        return render_status_pill("OK", "#0054a6", "info", size="10px")
    if score >= 40:
        return render_status_pill("WARN", "#d97706", "warning", size="10px")
    return render_status_pill("CRITICAL", "#dc2626", "cancel", size="10px")


def _get_repo_metadata_html(callback_context: CallbackContext) -> str:
    file_count = callback_context.state.get("logic_file_count", 0)
    module_map = callback_context.state.get("module_map", {})
    modules_count = len(module_map) if module_map else 0

    expert_count = sum(
        1
        for k in EXPERT_STATE_KEYS
        if (callback_context.state.get(k) or "").strip()
        and not (callback_context.state.get(k) or "").startswith("[SYSTEM_NOTE: Analysis skipped")
    )

    return f"""
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="p-6 bg-slate-50/50 rounded-2xl border border-slate-100 flex items-center justify-between">
                <div><p class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Source Logic</p><p class="text-2xl font-black text-slate-900">{file_count} Files</p></div>
                <span class="material-symbols-outlined text-slate-300">inventory_2</span>
            </div>
            <div class="p-6 bg-slate-50/50 rounded-2xl border border-slate-100 flex items-center justify-between">
                <div><p class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Architecture</p><p class="text-2xl font-black text-slate-900">{modules_count} Modules</p></div>
                <span class="material-symbols-outlined text-slate-300">account_tree</span>
            </div>
            <div class="p-6 bg-slate-50/50 rounded-2xl border border-slate-100 flex items-center justify-between">
                <div><p class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Expert Fleet</p><p class="text-2xl font-black text-slate-900">{expert_count:02d} Active</p></div>
                <span class="material-symbols-outlined text-slate-300">groups</span>
            </div>
        </div>
    """


def _structurize_expert_review(html: str) -> str:
    """Post-process rendered markdown to inject status pills and finding rows."""
    _PILL_RULES = [
        (
            r"(?i)\b(non[- ]compliant|fail(?:ed)?|violated|rejected|critical|p0)\b",
            "pill-fail",
        ),
        (r"(?i)\b(warn(?:ing)?|partial|review required|deprecated|p1)\b", "pill-warn"),
        (r"(?i)\b(compliant|pass(?:ed)?|approved|ok|verified|p2|p3)\b", "pill-pass"),
    ]

    def _wrap_inline(m):
        label, value = m.group(1), m.group(2).strip().rstrip(".")
        klass = next((css for pat, css in _PILL_RULES if re.search(pat, value)), "pill-info")
        return f'<strong>{label}:</strong> <span class="pill {klass}">{value}</span>'

    html = re.sub(
        r"<strong>(Finding|Status|Result|Severity|Compliance)[:：]?</strong>[:：]?\s*([A-Za-z][A-Za-z \-]{1,30}?)",
        _wrap_inline,
        html,
    )

    def _cardify(m):
        inner = m.group(1)
        k = "fail" if "pill-fail" in inner else "pass" if "pill-pass" in inner else ""
        return f'<div class="finding-row {k}">{inner}</div>'

    return re.sub(
        r"<p>((?:(?!</p>).)*?<strong>(?:Standard|Finding|Status|Result|Severity|Compliance)[:：]?</strong>(?:(?!</p>).)*?)</p>",
        _cardify,
        html,
        flags=re.DOTALL,
    )


def _render_expert_review_section(
    callback_context: CallbackContext, key: str, title: str, icon: str, accent: str
) -> str:
    import markdown as _md

    raw_body = (callback_context.state.get(key) or "").strip()

    if not raw_body or raw_body.startswith("[SYSTEM_NOTE: Analysis skipped"):
        logger.warning(f"Expert review section {key} ({title}) is empty or skipped.")
        return (
            f'<details class="expert-card-details mb-3 border border-slate-100 rounded-2xl bg-slate-50/40 opacity-55">'
            f'<summary class="flex items-center justify-between px-6 py-4 cursor-pointer select-none">'
            f'<span class="flex items-center gap-3">'
            f'<span class="w-8 h-8 rounded-xl bg-slate-100 flex items-center justify-center">'
            f'<span class="material-symbols-outlined text-slate-400 text-base">{icon}</span></span>'
            f'<span class="font-black text-slate-400 text-xs uppercase tracking-widest">{title}</span></span>'
            f'<span class="text-[9px] font-bold text-slate-300 uppercase tracking-widest">Skipped</span>'
            f"</summary></details>"
        )

    clean_body = re.sub(r"\[SYSTEM_NOTE:[^\]]+\]", "", raw_body).strip() or raw_body
    tokens = synthesis_token_manager.count_tokens(clean_body)
    rendered = _structurize_expert_review(_md.markdown(clean_body, extensions=["tables", "fenced_code", "sane_lists"]))

    # Map accent class → icon bg colour
    _bg_map = {
        "text-error": "bg-red-50",
        "text-primary": "bg-blue-50",
        "text-secondary": "bg-indigo-50",
        "text-tertiary": "bg-emerald-50",
    }
    icon_bg = _bg_map.get(accent, "bg-slate-50")

    return (
        f'<details class="expert-card-details mb-4 border border-slate-200 rounded-2xl bg-white shadow-sm overflow-hidden" open>'
        f'<summary class="flex items-center justify-between px-6 py-4 cursor-pointer select-none '
        f'bg-gradient-to-r from-slate-50/80 to-white border-b border-slate-100 hover:from-slate-100/60 transition-all">'
        f'<span class="flex items-center gap-4">'
        f'<span class="w-9 h-9 rounded-xl {icon_bg} border border-slate-100 flex items-center justify-center shadow-sm">'
        f'<span class="material-symbols-outlined {accent} text-xl" style="font-variation-settings:\'FILL\' 1">{icon}</span></span>'
        f'<div><span class="font-black text-slate-900 text-sm">{title}</span>'
        f'<span class="block text-[8px] font-bold text-slate-400 uppercase tracking-[0.15em] mt-0.5">Specialist Review</span></div></span>'
        f'<div class="flex items-center gap-3">'
        f'<span class="px-2.5 py-0.5 bg-slate-100 rounded-lg text-[8px] font-black text-slate-400 uppercase tracking-wider">{tokens:,} tokens</span>'
        f'<span class="expand-chevron material-symbols-outlined text-slate-300 text-sm">expand_more</span>'
        f"</div></summary>"
        f'<div class="px-8 py-6 expert-review-body">{rendered}</div></details>'
    )


# --- Template rendering -------------------------------------------------------


def _render_report_template(template: str, context: dict) -> str:
    """Render the report template via Jinja2; undefined variables render empty
    with a warning instead of leaking literal {{VAR}} into the report.

    Falls back to plain string replacement if the template ever gains syntax
    Jinja2 can't parse (e.g. stray braces in inline JS).
    """
    try:
        from jinja2 import ChainableUndefined, Environment

        class _LoggingUndefined(ChainableUndefined):
            def __str__(self) -> str:
                logger.warning(f"HTML Agent: template variable {self._undefined_name!r} has no value; rendered empty.")
                return ""

        env = Environment(undefined=_LoggingUndefined, autoescape=False)  # nosec B701
        return env.from_string(template).render(**context)
    except Exception as e:
        logger.warning(f"HTML Agent: Jinja2 render failed ({e}); using string replacement.")
        html = template
        for key, val in context.items():
            html = html.replace("{{" + key + "}}", str(val))
        leftover = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", html)))
        if leftover:
            logger.warning(f"HTML Agent: unreplaced template placeholders scrubbed: {leftover}")
            html = re.sub(r"\{\{[A-Z_]+\}\}", "", html)
        return html


# --- Self-contained asset inlining -------------------------------------------
#
# The report ships as a single, portable HTML artifact (emailed, archived,
# printed to PDF, opened from file://). It must not depend on external CDNs, so
# the Tailwind stylesheet, Chart.js and the (subsetted) Material Symbols icon
# font are inlined here. Assets live under templates/vendor/ and are rebuilt via
# tools/report_assets/ (`npm run build` for report.css, fetch_assets.ps1 for the
# JS + font). If a new icon name is added to the template/structurizers, re-run
# the font subset so its glyph is included.
#
# Inlining happens AFTER Jinja2 rendering, via plain string replacement on HTML
# comment sentinels — so Jinja never parses the asset bodies (minified JS/CSS is
# full of brace sequences that would otherwise blow up the {{ }} parser).

_VENDOR_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "vendor")


def _inline_report_assets(html: str) -> str:
    """Replace the <!--AG_*--> sentinels with the inlined vendor assets.

    A missing asset is logged and its sentinel left in place (a harmless HTML
    comment) rather than failing the whole report.
    """

    def _read_text(name: str) -> str | None:
        try:
            with open(os.path.join(_VENDOR_DIR, name), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"HTML Agent: vendor asset {name!r} unavailable ({e}); report will load it from no source.")
            return None

    # Tailwind utilities + base/components (compiled offline from the report's config).
    css = _read_text("report.css")
    if css is not None:
        html = html.replace("<!--AG_TAILWIND_CSS-->", f"<style>{css}</style>")

    # Chart.js UMD build. Neutralise any literal </script> in the bundle so it
    # can't terminate the inline <script> early (defensive; Chart.js has none).
    js = _read_text("chart.umd.min.js")
    if js is not None:
        js = js.replace("</script>", "<\\/script>")
        html = html.replace("<!--AG_CHART_JS-->", f"<script>{js}</script>")

    # Subsetted Material Symbols icon font, base64-inlined as @font-face. The
    # .material-symbols-outlined rule (font-family + ligatures) was previously
    # provided by the Google Fonts stylesheet, so it must be reproduced here.
    try:
        with open(os.path.join(_VENDOR_DIR, "material-symbols-subset.woff2"), "rb") as f:
            font_b64 = base64.b64encode(f.read()).decode("ascii")
        font_css = (
            "<style>"
            "@font-face{font-family:'Material Symbols Outlined';font-style:normal;"
            "font-weight:400;font-display:block;"
            "src:url(data:font/woff2;base64,__B64__) format('woff2');}"
            ".material-symbols-outlined{font-family:'Material Symbols Outlined';"
            "font-weight:normal;font-style:normal;font-size:24px;line-height:1;"
            "letter-spacing:normal;text-transform:none;display:inline-block;"
            "white-space:nowrap;word-wrap:normal;direction:ltr;"
            "font-feature-settings:'liga';-webkit-font-feature-settings:'liga';"
            "-webkit-font-smoothing:antialiased;}"
            "</style>"
        ).replace("__B64__", font_b64)
        html = html.replace("<!--AG_ICON_FONT-->", font_css)
    except Exception as e:
        logger.warning(f"HTML Agent: icon font unavailable ({e}); icons will render as text.")

    return html


# --- Callbacks --------------------------------------------------------------


async def prepare_html_context_callback(callback_context: CallbackContext):
    """Pre-run callback to prepare context for the Templated HTML report."""
    # First, enforce global token budget for injected keys
    await synthesis_budget_callback(callback_context)

    callback_context.state["current_date"] = datetime.datetime.now().strftime("%B %d, %Y")

    raw_m = callback_context.state.get("review_metrics", {})
    metrics = raw_m.model_dump() if hasattr(raw_m, "model_dump") else (raw_m if isinstance(raw_m, dict) else {})
    scores = metrics.get("scores", {})

    total_tokens = 0
    for key in EXPERT_STATE_KEYS:
        val = callback_context.state.get(key)
        if val is None:
            callback_context.state[key] = "[SYSTEM_NOTE: Analysis skipped.]"
            continue
        if isinstance(val, str):
            if any(err in val for err in ["429", "RESOURCE_EXHAUSTED"]):
                callback_context.state[key] = val + "\n\n[SYSTEM_NOTE: Session encountered 429 quota limits.]"
            total_tokens += synthesis_token_manager.count_tokens(val)

    overall = scores.get("overall")
    try:
        overall_val = float(overall)
    except (TypeError, ValueError):
        overall_val = 0
    if overall_val > 0:
        callback_context.state["scorecard_html"] = (
            f'<div class="flex items-center gap-3">{_get_score_badge(overall_val)}<span class="text-sm font-bold text-slate-400 uppercase tracking-widest">Policy Verification Score: {overall_val}/100</span></div>'
        )
        callback_context.state["report_grade"] = (
            "A" if overall_val >= 90 else "B" if overall_val >= 75 else "C" if overall_val >= 60 else "D"
        )
        callback_context.state["overall_score"] = str(int(overall_val))
    else:
        (
            callback_context.state["scorecard_html"],
            callback_context.state["report_grade"],
            callback_context.state["overall_score"],
        ) = "No score.", "U", "0"

    callback_context.state["repo_metadata_html"] = _get_repo_metadata_html(callback_context)
    callback_context.state["metrics_chart_html"] = ""

    expert_count_actual = sum(
        1
        for k, *_ in _EXPERT_SECTIONS
        if (callback_context.state.get(k) or "").strip()
        and not (callback_context.state.get(k) or "").startswith("[SYSTEM_NOTE: Analysis skipped")
    )

    # Calculate Dynamic Confidence Score
    confidence = 100.0
    if (callback_context.state.get("confluence_rules") or "").startswith("[CONFLUENCE_UNAVAILABLE]"):
        confidence -= 5.0  # Penalty for using built-in baseline vs live GRC

    expert_coverage = expert_count_actual / len(_EXPERT_SECTIONS)
    confidence *= expert_coverage  # Pro-rata confidence based on expert participation

    if (callback_context.state.get("code_logic") or "").startswith("[INGESTION_FAILED]"):
        confidence = 0.0  # Zero confidence if ingestion failed

    callback_context.state["confidence_score"] = f"{max(confidence, 0.0):.1f}"

    strategy = (callback_context.state.get("review_plan") or {}).get("strategy") or "all_experts_review_all"
    confluence_status = (
        "Unavailable"
        if (callback_context.state.get("confluence_rules") or "").startswith("[CONFLUENCE_UNAVAILABLE]")
        else f"{len(callback_context.state.get('confluence_rules', '')):,} chars"
    )

    # Confluence GRC status badge
    grc_ok = not (callback_context.state.get("confluence_rules") or "").startswith("[CONFLUENCE_UNAVAILABLE]")
    grc_badge = (
        '<span style="display:inline-flex;align-items:center;gap:4px;color:#16a34a;font-size:11px;font-weight:800;text-transform:uppercase;">&#10003; Live GRC</span>'
        if grc_ok
        else '<span style="display:inline-flex;align-items:center;gap:4px;color:#dc2626;font-size:11px;font-weight:800;text-transform:uppercase;">&#9888; Baseline</span>'
    )

    audit_trail_header = f"""
        {_EXPERT_REVIEW_STYLE}
        <div class="mb-10 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm">
                <p class="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">Expert Fleet</p>
                <p class="text-3xl font-black text-primary-900 leading-none mt-2">{expert_count_actual}<span class="text-base text-slate-300 font-bold"> / {len(_EXPERT_SECTIONS)}</span></p>
                <p class="text-[8px] text-slate-400 font-bold mt-2 uppercase">Specialists Active</p>
            </div>
            <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm">
                <p class="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">Ingested</p>
                <p class="text-3xl font-black text-primary-900 leading-none mt-2">{total_tokens:,}</p>
                <p class="text-[8px] text-slate-400 font-bold mt-2 uppercase">Tokens Processed</p>
            </div>
            <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm">
                <p class="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">Confluence GRC</p>
                <div class="mt-3">{grc_badge}</div>
                <p class="text-[8px] text-slate-400 font-bold mt-2 uppercase">{confluence_status}</p>
            </div>
            <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm">
                <p class="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">Strategy</p>
                <p class="text-[10px] font-black text-primary-700 mt-3 uppercase truncate" title="{strategy}">{strategy}</p>
                <p class="text-[8px] text-slate-400 font-bold mt-2 uppercase">Audit Mode</p>
            </div>
        </div>
    """
    callback_context.state["expert_reviews_html"] = audit_trail_header + "".join(
        _render_expert_review_section(callback_context, k, t, i, a) for k, t, i, a in _EXPERT_SECTIONS
    )


async def save_html_report_callback(callback_context: CallbackContext):
    """Post-run callback to assemble the final HTML from fragments and save it."""
    llm_resp = callback_context.state.get("html_report_content", "")
    if not llm_resp:
        return

    import markdown

    llm_resp = re.sub(r"^\s*```(?:html)?\s*\n?", "", llm_resp, flags=re.I | re.M)
    llm_resp = re.sub(r"\n?\s*```\s*$", "", llm_resp, flags=re.M).strip()

    def _match(tag: str) -> str:
        """Extract block between [TAG] and the next [TAG] marker using split-based approach."""
        marker = f"[{tag}]"
        idx = llm_resp.upper().find(marker.upper())
        if idx == -1:
            logger.warning("HTML report response missing [%s] block", tag)
            return ""
        after = llm_resp[idx + len(marker) :].lstrip(": \n")
        # Slice to the next known tag
        end = len(after)
        for other in ("TITLE", "SUMMARY", "CONTENT"):
            if other == tag:
                continue
            pos = after.upper().find(f"[{other}]")
            if pos != -1 and pos < end:
                end = pos
        return after[:end].strip()

    title = _match("TITLE") or "Precision Audit Report"

    # Process summary as markdown for better formatting and alignment
    summary_raw = _match("SUMMARY")
    if summary_raw:
        summary_html = f'<div class="reveal-on-scroll prose prose-slate max-w-none">{markdown.markdown(summary_raw, extensions=["fenced_code", "tables", "sane_lists"])}</div>'
    else:
        summary_html = '<p class="text-sm font-medium text-slate-500 italic">No summary provided.</p>'

    # Process content using the markdown-aware structurizer
    content_raw = _match("CONTENT") or llm_resp
    content_html = structurize_findings_html(content_raw)

    gov_raw = (callback_context.state.get("governance_review_result") or "").strip()
    governance_html = (
        structurize_governance_md(gov_raw)
        if gov_raw
        else '<p class="text-sm font-bold text-slate-400 uppercase tracking-widest py-12 text-center">Governance evidence unavailable.</p>'
    )

    # Count governance items using the same boundary patterns the structurizer uses
    rules_count = (
        len(_GOV_RULE_HEADER_RE.findall(gov_raw))
        or len(_GOV_ITEM_BOUNDARY_RE.findall(gov_raw))
        or len(_GOV_SECTION_HEADER_RE.findall(gov_raw))
        or 0
    )

    # Derive gate decision from governance text — single source of truth, reused
    # for both the hero badge and the Gate Decision pill so they never disagree.
    _gov_upper = gov_raw.upper()
    if any(
        k in _gov_upper
        for k in (
            "REJECTED",
            "HARD GATE FAIL",
            "GATE: FAIL",
            "GATE FAIL",
        )
    ):
        _gate_label, _gate_icon, _gate_color = "REJECTED", "cancel", "#dc2626"
    elif any(k in _gov_upper for k in ("CONDITIONAL", "CONDITIONS")):
        _gate_label, _gate_icon, _gate_color = "CONDITIONAL", "warning", "#d97706"
    elif any(
        k in _gov_upper
        for k in (
            "APPROVED",
            "CERTIFIED",
            "GATE: PASS",
            "GATE PASS",
            "GATE DECISION: PASS",
        )
    ):
        _gate_label, _gate_icon, _gate_color = "CERTIFIED", "verified", "#16a34a"
    else:
        _gate_label, _gate_icon, _gate_color = "Review", "warning", "#d97706"
    gate_decision_html = render_status_pill(_gate_label, _gate_color, _gate_icon, size="12px")

    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "report_template.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except Exception as e:
        logger.error(f"Failed to load template: {e}")
        callback_context.state["html_report_content"] = f"Report generation failed: {str(e)}"
        return

    def _img(n: str) -> str:
        try:
            candidates = [
                os.path.join(os.path.dirname(__file__), "..", "templates", "image", n),
                os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", n),
            ]
            for p in candidates:
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        data = base64.b64encode(f.read()).decode("utf-8")
                        mime = "image/svg+xml" if n.endswith(".svg") else "image/png"
                        return f"data:{mime};base64,{data}"
        except Exception:
            return ""
        return ""

    l_src = _img("agent-guardian-logo.svg") or _img("agent-guardian-logo.png")
    a_src = _img("google-adk.png")

    status_badge = render_status_pill(_gate_label, _gate_color, _gate_icon, size="13px")

    context = {
        "LOGO": l_src or "",
        "ADK_ICON": a_src or "",
        "TITLE": title or "",
        "DATE": callback_context.state.get("current_date", "") or "",
        "OVERALL_SCORE": callback_context.state.get("overall_score", "0") or "0",
        "GRADE": callback_context.state.get("report_grade", "U") or "U",
        "RULES_COUNT": str(rules_count),
        "CONFIDENCE_SCORE": callback_context.state.get("confidence_score", "0.0") or "0.0",
        "EXECUTIVE_SUMMARY": summary_html or "",
        "GATE_DECISION_HTML": gate_decision_html,
        "SCORE_BADGE_HTML": callback_context.state.get("scorecard_html", "") or "",
        "SCORECARD_HTML": governance_html or "",
        "REPO_METADATA_HTML": callback_context.state.get("repo_metadata_html", "") or "",
        "METRICS_CHART_HTML": callback_context.state.get("metrics_chart_html", "") or "",
        "METRICS_JSON": callback_context.state.get("metrics_json", "{}") or "{}",
        "CONTENT_HTML": content_html or "",
        "EXPERT_REVIEWS_HTML": callback_context.state.get("expert_reviews_html", "") or "",
        "STATUS_DISPLAY": status_badge,
    }
    final_html = _render_report_template(template, context)
    final_html = _inline_report_assets(final_html)

    artifact = types.Part(inline_data=types.Blob(data=final_html.encode("utf-8"), mime_type="text/html"))
    # Use a short, stable filename. The title-derived name (up to 40 chars) was
    # repeated inside the artifact path by ADK's FileArtifactService
    # (`<root>/.../artifacts/<name>/versions/0/<name>`); combined with a long
    # working directory (e.g. a OneDrive-synced path) it overflowed Windows'
    # 260-char MAX_PATH, so the content file write failed and every download
    # 404'd. A short fixed name keeps the path well under the limit.
    report_filename = "report.html"
    try:
        await callback_context.save_artifact(filename=report_filename, artifact=artifact)
        logger.info(f"HTML Agent: Successfully saved report artifact to {report_filename}")
    except Exception as e:
        logger.warning(f"HTML Agent: Failed to save report artifact (Artifact service may be uninitialized): {e}")
    callback_context.state["html_report_content"] = final_html
    callback_context.state["report_artifact_name"] = report_filename


# Build a specific config for the HTML agent to support large, detailed reports.
# Low temperature: templated HTML assembly must be precise, not creative.
_html_config = _cfg.generation_config(temperature=_cfg.agent_settings.html_temperature)
_html_config.max_output_tokens = 32768

html_agent = LlmAgent(
    name="html_agent",
    # Full Flash tier — lite models truncate on 30-40 KB structured reports.
    model=_cfg.agent_settings.html_model,
    description="Assembles a premium, high-fidelity HTML report using content fragments and a base template.",
    instruction=HTML_REPORT_PROMPT,
    output_key="html_report_content",
    include_contents="none",
    before_agent_callback=prepare_html_context_callback,
    after_agent_callback=save_html_report_callback,
    generate_content_config=_html_config,
)
