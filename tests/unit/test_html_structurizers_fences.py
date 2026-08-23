"""Fenced code blocks must never be parsed as findings/rules or split apart.

Regression tests for the report bugs where:
  * requirements pins inside a ``` fence ("google-adk==0.1.25") became bogus
    governance rule cards (ids="google", title="adk");
  * a finding label match in mid-fence collapsed the fence, leaking the
    language tag ("python") as prose and rendering in-code "#" comments as
    giant <h1> headings.
"""

from agent_guardian.utils.html_structurizers import (
    structurize_findings_html,
    structurize_governance_md,
)


GOV_WITH_REQUIREMENTS_FENCE = """\
**Verdict:** REJECTED

1. DEPENDENCY AUDIT

❌ Item 1: Unpinned dependencies
**Observation:** The requirements file uses unpinned versions.
**Required Action:** Pin all versions:

```text
google-adk==0.1.25  # Replace with latest approved version
google-cloud-bigquery==3.27.0
pydantic==2.10.4
requests
status: str
```

**Severity:** HIGH
"""


FINDING_WITH_PYTHON_FENCE = """\
1. CRITICAL: SQL Injection Vulnerabilities

**Observation:** String-based SQL query construction using f-strings in `tools.py`.
**Violation:** Bandit-B608 (SQL Injection Risk).
**Required Action:** Refactor all database queries to use parameterized inputs.

```python
# Violation in tools.py
query = f"SELECT * FROM returns WHERE id = '{complaint_id}'"
cursor.execute(query)
```

2. HIGH: Hardcoded Secrets

**Observation:** Email addresses present in config.

```python
# Before
RECEIVER_EMAIL = "team@example.com"
# After
secrets = _get_secret(project, "credentials")
```
"""


def test_requirements_fence_does_not_become_rule_cards():
    html = structurize_governance_md(GOV_WITH_REQUIREMENTS_FENCE)
    # No bogus per-dependency cards: "google" must never be a rule id / number.
    assert '<span class="finding-num">google</span>' not in html
    assert '<span class="finding-num">status</span>' not in html
    # The fence must survive intact as a rendered code block.
    assert "google-adk==0.1.25" in html
    assert "<code" in html or "<pre" in html
    # No masking tokens may leak into the output.
    assert "\x00" not in html
    assert "FENCE" not in html


def test_python_fence_not_split_by_finding_labels():
    html = structurize_findings_html(FINDING_WITH_PYTHON_FENCE)
    # Both findings render as cards.
    assert 'data-severity="CRITICAL"' in html
    assert 'data-severity="HIGH"' in html
    # The code comment must stay inside a code block — never become a heading.
    assert "<h1>" not in html and "<h2>" not in html
    assert "complaint_id" in html
    # The fence language tag must not leak as prose right after the action text.
    assert "parameterized inputs.</p>\n<p>python" not in html
    assert "\x00" not in html


def test_uppercase_rule_ids_still_parse():
    md = "GOV-01 | Model pinning | ❌ FAIL (-10)\n**Finding:** Model version not pinned.\n"
    html = structurize_governance_md(md)
    assert "GOV-01" in html
    assert "Model pinning" in html


FINDING_WITH_FENCE_INSIDE_ACTION_BUCKET = """\
1. [CRITICAL] SEC-001: Insecure Deserialization

**Violation:** All credentials must be injected via Secret Manager; `ast.literal_eval` is a risk.
**Required Action:** Replace `ast.literal_eval` with `json.loads()` in api/main.py.

```python
secrets = ast.literal_eval(payload)  # Insecure parsing
```
"""


def test_fence_inside_action_bucket_renders_as_code_block():
    """Regression: a fence following prose on the same **Required Action:**
    bucket line got masked to a single-line token, then rejoined mid-line
    with that prose. Markdown's fenced_code extension only recognizes a
    fence that starts its own line, so the restored fence fell through as
    flat, unhighlighted paragraph text (the "python ... secrets = ast."
    prose seen in the rendered report) instead of a <pre><code> block.
    """
    html = structurize_findings_html(FINDING_WITH_FENCE_INSIDE_ACTION_BUCKET)
    assert "<pre" in html
    assert "secrets = ast.literal_eval(payload)" in html
    assert "\x00" not in html
    assert "FENCE" not in html
