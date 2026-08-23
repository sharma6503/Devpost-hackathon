"""Report-template rendering: no {{VAR}} may ever leak into the final HTML."""

import logging
import re
from unittest.mock import MagicMock

from agent_guardian.sub_agents.html_agent import (
    _render_report_template,
    _render_expert_review_section,
)


def _placeholders_in(html: str) -> list[str]:
    return re.findall(r"\{\{[A-Z_]+\}\}", html)


def test_all_known_placeholders_replaced():
    template = "<h1>{{TITLE}}</h1><p>{{DATE}}</p><div>{{CONTENT_HTML}}</div>"
    out = _render_report_template(
        template,
        {"TITLE": "Audit", "DATE": "June 11, 2026", "CONTENT_HTML": "<b>ok</b>"},
    )
    assert "Audit" in out and "<b>ok</b>" in out
    assert _placeholders_in(out) == []


def test_undefined_placeholder_renders_empty_not_literal():
    template = "<h1>{{TITLE}}</h1><span>{{NEWLY_ADDED_VAR}}</span>"
    out = _render_report_template(template, {"TITLE": "Audit"})
    assert "Audit" in out
    assert "NEWLY_ADDED_VAR" not in out
    assert _placeholders_in(out) == []


def test_real_template_renders_without_leftovers():
    import os

    template_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "agent_guardian",
        "templates",
        "report_template.html",
    )
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    keys = [
        "LOGO",
        "ADK_ICON",
        "TITLE",
        "DATE",
        "OVERALL_SCORE",
        "GRADE",
        "RULES_COUNT",
        "CONFIDENCE_SCORE",
        "EXECUTIVE_SUMMARY",
        "GATE_DECISION_HTML",
        "SCORE_BADGE_HTML",
        "SCORECARD_HTML",
        "REPO_METADATA_HTML",
        "METRICS_JSON",
        "CONTENT_HTML",
        "EXPERT_REVIEWS_HTML",
        "STATUS_DISPLAY",
    ]
    out = _render_report_template(template, {k: f"VALUE_{k}" for k in keys})
    assert _placeholders_in(out) == []
    assert "VALUE_TITLE" in out


def test_expert_section_logs_warning_when_empty(caplog):
    ctx = MagicMock()
    ctx.state = {"quality_review_result": ""}
    with caplog.at_level(logging.WARNING):
        html = _render_expert_review_section(
            ctx, "quality_review_result", "Code Quality", "code_blocks", "text-primary"
        )
    assert "quality_review_result" in caplog.text
    assert "Code Quality" in caplog.text
    assert "Skipped" in html


def test_expert_section_no_warning_when_populated(caplog):
    ctx = MagicMock()
    ctx.state = {"quality_review_result": "## Findings\n\nLooks good."}
    with caplog.at_level(logging.WARNING):
        html = _render_expert_review_section(
            ctx, "quality_review_result", "Code Quality", "code_blocks", "text-primary"
        )
    agent_guardian_warnings = [
        r for r in caplog.records if r.levelno >= logging.WARNING and r.name.startswith("agent_guardian")
    ]
    assert len(agent_guardian_warnings) == 0
    assert "Looks good" in html
