from __future__ import annotations
import json
from agent_guardian.tools.governance_tools import (
    scan_regex,
    audit_dependencies,
    analyze_ast,
    scan_governance,
)


def test_scan_regex(sample_python_code):
    findings = scan_regex(sample_python_code)
    # Expecting the hardcoded Google API key to be found
    assert any("AIzaSyA1234567890" in f["match"] for f in findings)
    assert any(f["line"] == 7 for f in findings)


def test_audit_dependencies(sample_requirements):
    findings = audit_dependencies(sample_requirements)
    # fastapi and google-adk are not pinned with ==
    packages_with_issues = [f["package"] for f in findings]
    assert "fastapi" in packages_with_issues
    assert "google-adk>=1.31.1" in packages_with_issues
    assert "requests==2.31.0" not in packages_with_issues


def test_analyze_ast(sample_python_code):
    findings = analyze_ast(sample_python_code)
    # Expecting: External call missing explicit timeout
    assert any("missing explicit timeout" in f["issue"].lower() for f in findings)
    assert any(f["func"] == "get" for f in findings)


def test_scan_governance_integration(sample_python_code):
    # Test the dispatcher
    result_json = scan_governance("test.py", sample_python_code, "regex_scan")
    results = json.loads(result_json)
    assert len(results) > 0
    assert results[0]["match"] == 'api_key = "AIzaSyA1234567890"'
