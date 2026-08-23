from __future__ import annotations

"""
Code Validator Agent — Deterministic Static Analysis Expert.

Role in Pipeline:
Executes within the `parallel_review_experts` group during the Quality Gate Loop.
Runs real, execution-free static analyzers over the ingested code (via the
`run_static_analysis` tool) and interprets the deterministic findings into a
review. This replaced the sandboxed `BuiltInCodeExecutor`, which could only run
isolated snippets it wrote itself (never the audited repo), was non-deterministic,
and was the pipeline's most failure-prone node.

State Interactions:
- Reads: `code_logic`, `source_artifact_path`
- Writes: `validation_result`
"""

from google.adk.agents import LlmAgent
from ..config import Config
from ..prompts import CODE_VALIDATOR_PROMPT
from ..tools import run_static_analysis

_cfg = Config()

code_validator_agent = LlmAgent(
    name="code_validator_agent",
    model=_cfg.agent_settings.validator_model,
    description="Validates code via deterministic static analysis (no execution).",
    instruction=CODE_VALIDATOR_PROMPT,
    tools=[run_static_analysis],
    output_key="validation_result",
    include_contents="none",  # all input comes via state injection / the tool
    generate_content_config=_cfg.safety_config,
)
