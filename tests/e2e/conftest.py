import pytest
import json
from unittest.mock import AsyncMock, patch

from agent_guardian.utils.compat import SafeMcpToolset

from google.genai import types as genai_types


@pytest.fixture(autouse=True)
def mock_mcp_and_token_manager():
    """Mocks MCP toolsets and TokenManager to avoid background tasks and network calls."""
    with patch("agent_guardian.utils.token_utils.TokenManager") as mock_tm_class, \
         patch.object(SafeMcpToolset, "get_tools", AsyncMock(return_value=[])), \
         patch.object(SafeMcpToolset, "get_tools_with_prefix", AsyncMock(return_value=[])), \
         patch.object(SafeMcpToolset, "close", AsyncMock()):
        mock_tm = mock_tm_class.return_value
        mock_tm.count_tokens.return_value = 10
        mock_tm.is_over_budget.return_value = False
        yield


@pytest.fixture(autouse=True)
def mock_confluence_prefetch():
    """Automatically mocks Confluence pre-fetch to avoid network calls during tests."""
    with patch(
        "agent_guardian.sub_agents.confluence_rules_agent._prefetch_all_pages",
        return_value=True,
    ):
        with patch(
            "agent_guardian.sub_agents.confluence_rules_agent._PREFETCH_CACHE",
            {"confluence_rules": "# Mocked Rules"},
        ):
            yield


@pytest.fixture
def mock_genai_client():
    """Globally mocks the Gemini LLM client for E2E tests."""
    with patch("google.genai.Client") as mock_class:
        mock_client = mock_class.return_value

        # We'll use a side_effect to return different responses based on the prompt/agent
        async def side_effect(*args, **kwargs):
            kwargs.get("model") or (args[0] if len(args) > 0 else "unknown")
            contents = kwargs.get("contents") or (args[1] if len(args) > 1 else "")
            config = kwargs.get("config") or kwargs.get("generate_content_config")

            content_str = str(contents).lower()
            sys_inst = ""
            if config:
                sys_inst_val = getattr(config, "system_instruction", None)
                if sys_inst_val:
                    sys_inst = str(sys_inst_val).lower()

            # If ADK is calling back after a tool was already executed, the contents will
            # contain a function_response part. Return a terminal text response immediately
            # to avoid infinite function-call loops (which hit the 500-call safety limit).
            if "function_response" in content_str:
                if sys_inst and ("ingest" in sys_inst or "unzip" in sys_inst or "extraction" in sys_inst):
                    return _create_mock_response(
                        text=(
                            "=== DIRECTORY STRUCTURE ===\n"
                            "  [LOGIC]\n    main.py\n"
                            "  [CONFIG]\n    requirements.txt\n"
                            "  [DOCS]\n    README.md\n"
                            "=== FILE CONTENTS ===\n"
                            "--- main.py ---\nprint('hello world')\n"
                            "--- requirements.txt ---\ngoogle-adk==1.0.0\n"
                            "--- README.md ---\n# Dummy Project\n"
                        )
                    )
                # For any other agent with a tool response, return "done" text
                return _create_mock_response(text="Analysis complete.")

            # First, match by system instruction if available
            if sys_inst:
                # 1. Supervisor / Root Agent (MUST BE FIRST to avoid matching mentioned orchestration/metrics terms)
                if "guardian supervisor" in sys_inst or "root_agent" in sys_inst:
                    if "zip" in content_str:
                        return _create_mock_response(
                            function_call=genai_types.FunctionCall(
                                name="transfer_to_agent",
                                args={"agent_name": "review_pipeline"},
                            )
                        )
                    return _create_mock_response(text="I am ready to review. Please share a GitHub URL or ZIP.")

                # 2. Ingestion Agent
                elif "ingest" in sys_inst or "unzip" in sys_inst or "extraction" in sys_inst:
                    return _create_mock_response(
                        function_call=genai_types.FunctionCall(
                            name="parse_uploaded_files",
                            args={"file_paths": ["/tmp/dummy.zip"]},
                        )
                    )

                # 3. Planning Agent
                elif "planner" in sys_inst or "planning" in sys_inst or "plan_generation" in sys_inst:
                    mock_plan = {
                        "is_large_codebase": False,
                        "strategy": "E2E Mock: standard review of all modules",
                        "assignments": [
                            {
                                "expert_name": "quality_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "Code quality scan",
                            },
                            {
                                "expert_name": "security_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "Security audit",
                            },
                            {
                                "expert_name": "governance_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "Governance audit",
                            },
                            {
                                "expert_name": "adk_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "ADK audit",
                            },
                        ],
                    }
                    return _create_mock_response(text=json.dumps(mock_plan))

                # 4. Evaluation Expert — must come BEFORE generic "expert" catch-all because the
                #    evaluation prompt also contains the word "expert". Use its unique keywords.
                elif (
                    "evaluation" in sys_inst
                    or "quality gate" in sys_inst
                    or "specificity" in sys_inst
                    or "scoring rubric" in sys_inst
                ):
                    eval_result = {
                        "scores": [
                            {
                                "agent": "quality_expert",
                                "specificity": 8,
                                "evidence": 8,
                                "actionability": 8,
                                "avg": 8.0,
                            }
                        ],
                        "overall_grade": "PASS",
                        "weakest_agent": None,
                        "weakest_dimension": None,
                        "remediation_required": False,
                        "feedback": "All reviews meet the quality threshold.",
                    }
                    return _create_mock_response(text=json.dumps(eval_result))

                # 5. Metrics Agent
                elif "metrics" in sys_inst:
                    metrics_result = {
                        "overall_score": 85,
                        "dimension_scores": {"security": 90, "quality": 80},
                        "rule_violations": [],
                    }
                    return _create_mock_response(text=json.dumps(metrics_result))

                # 6. HTML Agent
                elif "html" in sys_inst or "dashboard" in sys_inst:
                    return _create_mock_response(text="<html><body>Audit Report</body></html>")

                # 7. Synthesis Agent
                elif "synthesis" in sys_inst or "aggregate" in sys_inst or "consolidate" in sys_inst:
                    return _create_mock_response(text="# Comprehensive Review\nAll good.")

                # 8. Experts (Security, Quality, etc.)
                elif "expert" in sys_inst or "audit" in sys_inst or "finding" in sys_inst:
                    return _create_mock_response(
                        text="Review finding: Found a potential issue in main.py. Fix by using a better pattern."
                    )

                # Default fallback for unrecognized agent with sys_inst
                else:
                    return _create_mock_response(text="Acknowledged.")

            else:
                # Fallback to heuristic content_str matching if sys_inst is empty

                # 1. Ingestion Agent
                if "ingest" in content_str or "fetch" in content_str or "parse" in content_str:
                    # MUST return a function call so the callback finds tool results
                    return _create_mock_response(
                        function_call=genai_types.FunctionCall(
                            name="parse_uploaded_files",
                            args={"file_paths": ["/tmp/dummy.zip"]},
                        )
                    )

                # 2. Planning Agent
                elif "plan" in content_str or "assign" in content_str:
                    mock_plan = {
                        "is_large_codebase": False,
                        "strategy": "E2E Mock: standard review of all modules",
                        "assignments": [
                            {
                                "expert_name": "quality_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "Code quality scan",
                            },
                            {
                                "expert_name": "security_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "Security audit",
                            },
                            {
                                "expert_name": "governance_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "Governance audit",
                            },
                            {
                                "expert_name": "adk_expert",
                                "assigned_modules": ["all"],
                                "focus_areas": "ADK audit",
                            },
                        ],
                    }
                    return _create_mock_response(text=json.dumps(mock_plan))

                # 3. Evaluation Expert (CRITICAL: Must return valid EvaluationResult JSON)
                elif "evaluation" in content_str or "quality gate" in content_str or "specificity" in content_str:
                    eval_result = {
                        "scores": [
                            {
                                "agent": "quality_expert",
                                "specificity": 8,
                                "evidence": 8,
                                "actionability": 8,
                                "avg": 8.0,
                            }
                        ],
                        "overall_grade": "PASS",
                        "weakest_agent": None,
                        "weakest_dimension": None,
                        "remediation_required": False,
                        "feedback": "All reviews meet the quality threshold.",
                    }
                    return _create_mock_response(text=json.dumps(eval_result))

                # 4. Experts (Security, Quality, etc.)
                elif "expert" in content_str or "audit" in content_str or "finding" in content_str:
                    return _create_mock_response(
                        text="Review finding: Found a potential issue in main.py. Fix by using a better pattern."
                    )

                # 5. Synthesis Agent
                elif "synthesise" in content_str or "aggregate" in content_str or "consolidate" in content_str:
                    return _create_mock_response(text="# Comprehensive Review\nAll good.")

                # 6. Metrics Agent (Must return valid ReviewMetrics JSON)
                elif "metrics" in content_str or "score" in content_str:
                    metrics_result = {
                        "overall_score": 85,
                        "dimension_scores": {"security": 90, "quality": 80},
                        "rule_violations": [],
                    }
                    return _create_mock_response(text=json.dumps(metrics_result))

                # 7. HTML Agent
                elif "html" in content_str or "dashboard" in content_str:
                    return _create_mock_response(text="<html><body>Audit Report</body></html>")

                # 8. Supervisor / Root Agent (MUST BE LAST)
                else:
                    has_supervisor = "supervisor" in content_str
                    has_review = "review" in content_str
                    has_zip = "zip" in content_str
                    print(
                        f"DEBUG_FALLBACK: has_supervisor={has_supervisor}, has_review={has_review}, has_zip={has_zip}"
                    )
                    if has_supervisor or has_review or has_zip:
                        if has_zip:
                            print("DEBUG_FALLBACK: matched supervisor + zip, returning transfer_to_agent")
                            # If it's the root agent and we see "zip", transfer to pipeline
                            return _create_mock_response(
                                function_call=genai_types.FunctionCall(
                                    name="transfer_to_agent",
                                    args={"agent_name": "review_pipeline"},
                                )
                            )
                        print("DEBUG_FALLBACK: matched supervisor no zip, returning ready message")
                        return _create_mock_response(text="I am ready to review. Please share a GitHub URL or ZIP.")

                    # Default fallback
                    return _create_mock_response(text="Acknowledged.")

        mock_client.models.generate_content = AsyncMock(side_effect=side_effect)
        mock_client.aio.models.generate_content = AsyncMock(side_effect=side_effect)
        try:
            yield mock_client
        finally:
            try:
                from agent_guardian.agent import root_agent

                def _clear_agent_clients(agent):
                    if agent is None:
                        return
                    if hasattr(agent, "_resolved_model"):
                        agent._resolved_model = None
                    if hasattr(agent, "inner_agent"):
                        _clear_agent_clients(agent.inner_agent)
                    if hasattr(agent, "sub_agents"):
                        for sa in agent.sub_agents:
                            _clear_agent_clients(sa)
                    if hasattr(agent, "workflow"):
                        for u, v in getattr(agent.workflow, "edges", []):
                            _clear_agent_clients(u)
                            _clear_agent_clients(v)

                _clear_agent_clients(root_agent)
            except Exception:
                pass


def _create_mock_response(text=None, function_call=None):
    from google.genai import types as genai_types

    parts = []
    if text:
        parts.append(genai_types.Part.from_text(text=text))
    if function_call:
        parts.append(genai_types.Part(function_call=function_call))

    candidate = genai_types.Candidate(content=genai_types.Content(role="model", parts=parts), finish_reason="STOP")

    return genai_types.GenerateContentResponse(
        candidates=[candidate],
        model_version="gemini-test",
        usage_metadata=genai_types.UsageMetadata(prompt_token_count=10, response_token_count=10, total_token_count=20),
    )
