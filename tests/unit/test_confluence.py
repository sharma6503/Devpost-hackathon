"""
test_confluence.py — Unit tests for Confluence HTML-to-Markdown conversion.
"""

from __future__ import annotations

from unittest.mock import patch
from agent_guardian.utils.confluence_rest import _strip_html


def test_strip_html_markdownify():
    """Verify that _strip_html correctly uses markdownify when available to produce structured MD."""
    html_input = "<h1>My Title</h1><p>This is <strong>bold</strong> text and a <a href='http://example.com'>link</a>.</p><ul><li>Item 1</li><li>Item 2</li></ul>"

    md_output = _strip_html(html_input)

    # Check that headings, bold, link, and lists are converted as Markdown
    assert "# My Title" in md_output
    assert "**bold**" in md_output or "__bold__" in md_output
    assert "[link](http://example.com)" in md_output
    assert "- Item 1" in md_output or "* Item 1" in md_output


def test_strip_html_fallback():
    """Verify that _strip_html falls back gracefully to a basic HTML stripper if markdownify fails."""
    html_input = "<h1>My Title</h1><p>This is <strong>bold</strong> text and a <a href='http://example.com'>link</a>.</p><ul><li>Item 1</li><li>Item 2</li></ul>"

    # Force markdownify to raise an exception to trigger the fallback
    with patch("markdownify.markdownify", side_effect=Exception("Mock markdownify failure")):
        md_output = _strip_html(html_input)

        # Fallback should still strip html tags and decode entities
        assert "<" not in md_output
        assert ">" not in md_output
        assert "My Title" in md_output
        assert "bold" in md_output
        assert "link" in md_output
        assert "Item 1" in md_output
