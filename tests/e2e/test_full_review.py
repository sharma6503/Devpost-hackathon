import pytest
import os
import zipfile
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from agent_guardian.agent import root_agent
from google.genai import types as genai_types


@pytest.fixture
def mock_session_service():
    return InMemorySessionService()


@pytest.fixture
def dummy_zip_file():
    """Creates a temporary dummy ZIP file for ingestion testing."""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr("main.py", "print('hello world')")
            z.writestr("requirements.txt", "google-adk==1.0.0")
            z.writestr("README.md", "# Dummy Project")
        return tmp.name


@pytest.mark.asyncio
async def test_full_review_e2e(mock_session_service, mock_genai_client, dummy_zip_file):
    """
    E2E Test: Simulates a full review cycle from ZIP upload to HTML report.
    This test uses a mocked LLM (from conftest) and mocked tools.
    """
    user_id = "e2e_user"
    session_id = "e2e_session"
    await mock_session_service.create_session(app_name="agent_guardian", user_id=user_id, session_id=session_id)

    # Tools to mock
    mock_tools = {
        "agent_guardian.tools.parse_uploaded_files": MagicMock(
            return_value={
                "status": "success",
                "file_count": 3,
                "codebase": "--- main.py ---\nprint('hello world')\n--- requirements.txt ---\ngoogle-adk==1.0.0\n--- README.md ---\n# Dummy Project",
                "summary": {
                    "logic": ["main.py"],
                    "config": ["requirements.txt"],
                    "docs": ["README.md"],
                },
            }
        ),
        "agent_guardian.tools.read_artifact_file": AsyncMock(return_value={"content": "print('hello world')"}),
        "agent_guardian.tools.governance_tools.scan_governance": MagicMock(return_value={"findings": []}),
        "agent_guardian.sub_agents.confluence_rules_agent.fetch_page_by_id": AsyncMock(
            return_value={"markdown": "# Rules", "page_id": "123", "error": ""}
        ),
    }

    from agent_guardian.sub_agents.ingestion_agent import ingestion_agent

    # Direct patch of ingestion_agent.tools list to ensure ADK's internal references invoke the mock
    original_tools = list(ingestion_agent.tools)
    for i, tool in enumerate(ingestion_agent.tools):
        if getattr(tool, "__name__", "") == "parse_uploaded_files":
            ingestion_agent.tools[i] = mock_tools["agent_guardian.tools.parse_uploaded_files"]
        elif getattr(tool, "__name__", "") == "read_artifact_file":
            ingestion_agent.tools[i] = mock_tools["agent_guardian.tools.read_artifact_file"]

    try:
        # Apply all tool mocks
        with patch.multiple(
            "agent_guardian.sub_agents.ingestion_agent",
            parse_uploaded_files=mock_tools["agent_guardian.tools.parse_uploaded_files"],
            read_artifact_file=mock_tools["agent_guardian.tools.read_artifact_file"],
        ):
            with patch(
                "agent_guardian.sub_agents.confluence_rules_agent.fetch_page_by_id",
                mock_tools["agent_guardian.sub_agents.confluence_rules_agent.fetch_page_by_id"],
            ):
                runner = Runner(
                    agent=root_agent,
                    app_name="agent_guardian",
                    session_service=mock_session_service,
                )

                # Start the review by attaching the ZIP file
                # In a real adk web session, the ZIP is passed as inline_data/file_data.
                # Our constitution_callback intercepts ZIP parts and saves them to state.

                # Simulate the user sending the ZIP file
                query = f"Review this ZIP: {dummy_zip_file}"

                # We'll run the runner and collect all events
                final_response = ""
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=genai_types.Content(
                        role="user",
                        parts=[
                            genai_types.Part.from_text(text=query),
                            # Simulate ZIP attachment
                            genai_types.Part(
                                inline_data=genai_types.Blob(mime_type="application/zip", data=b"fake-zip-data")
                            ),
                        ],
                    ),
                ):
                    print(
                        f"EVENT: author={getattr(event, 'author', None)} actions={getattr(event, 'actions', None)} fields={list(getattr(event, '__dict__', {}).keys()) or getattr(event, 'model_fields', {}).keys()}".encode(
                            "ascii", errors="replace"
                        ).decode("ascii")
                    )
                    if getattr(event, "content", None) and event.content.parts:
                        for p in event.content.parts:
                            p_text = getattr(p, "text", "") or ""
                            print(
                                f"  PART text={p_text[:100]} func_call={getattr(p, 'function_call', None)} func_resp={getattr(p, 'function_response', None)}".encode(
                                    "ascii", errors="replace"
                                ).decode("ascii")
                            )
                    if event.is_final_response() and getattr(event, "content", None) and event.content.parts:
                        final_response = getattr(event.content.parts[0], "text", "") or ""

                # 4. Assertions
                session = await mock_session_service.get_session(
                    app_name="agent_guardian", user_id=user_id, session_id=session_id
                )

                # Verify pipeline stages were completed
                assert "html_report_content" in session.state, "html_report_content missing from state"
                assert "synthesis_result" in session.state, "synthesis_result missing from state"
                assert session.state["total_file_count"] > 0, "total_file_count should be > 0 after ingestion"

                # Verify the pipeline produced a non-empty final response.
                # We check content rather than exact text because the mock LLM returns
                # fixed strings — real content assertions belong in prompt/integration tests.
                assert final_response, "Expected a non-empty final response from the pipeline"
    finally:
        ingestion_agent.tools = original_tools
        # Cleanup
        if os.path.exists(dummy_zip_file):
            os.remove(dummy_zip_file)
