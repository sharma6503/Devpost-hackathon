
### 📄 Per-Page Confluence Validation Protocol (STRICT & MANDATORY)

The `{confluence_rules}` block is composed of one or more delimited sections,
one per Confluence page. Each section begins with a header line of the form:

    === CONFLUENCE RULES: <Page Title> (page_id=<id>) ===

The index of available pages is in `{confluence_pages_index}`.

**CRITICAL: DO NOT SUMMARIZE.** Your task is to VALIDATE the codebase against the EXACT requirements, policies, and governance standards defined in each page. You must treat these as "Hard Rules," not as general advice or context to be summarized.

You MUST:
1. **Iterate every section.** Treat each `=== CONFLUENCE RULES: ... ===`
   block as an INDEPENDENT and AUTHORITATIVE rule source. Do NOT merge them.
2. **Validate the codebase against EACH page separately.** Produce a distinct
   per-page subsection in your findings, using this exact heading format:

       #### 📘 Page: <Page Title> (page_id=<id>)

   followed by that page's findings table or bullet list.
3. **Exact Rule Citation.** Every finding MUST cite the specific rule or policy text found in the Confluence page. Do not paraphrase the rule; use the exact terminology or short quote from the page.
4. **No Content Loss.** Ensure that NO policy or rule from the page is ignored. If a rule exists on the page, the codebase must be checked against it.
5. **Do not skip pages.** If a page contains no applicable rules for your
   domain, output:

       #### 📘 Page: <Page Title> (page_id=<id>)
       _No applicable rules in this page for the current review scope._

6. If `{confluence_rules}` equals `CONFLUENCE_UNAVAILABLE: ...`, skip this
   protocol and rely on your built-in fallback ruleset.

This protocol is REQUIRED. A review that summarizes the rules, paraphrases policies into vague "advice," or omits per-page subsections will be marked FAIL by the evaluation_expert.
