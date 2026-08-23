import pytest
from unittest.mock import AsyncMock, patch
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from agent_guardian.agent import root_agent
from google.genai import types as genai_types


@pytest.fixture
def mock_session_service():
    return InMemorySessionService()


@pytest.mark.asyncio
async def test_root_agent_delegation(mock_session_service):
    """Verify that root_agent correctly delegates to review_pipeline when code is provided."""

    # 1. Setup the session
    user_id = "user_123"
    session_id = "session_456"
    await mock_session_service.create_session(app_name="agent_guardian", user_id=user_id, session_id=session_id)

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
            usage_metadata=genai_types.UsageMetadata(
                prompt_token_count=10, response_token_count=10, total_token_count=20
            ),
        )

    # 2. Mock the LLM Response for root_agent
    mock_transfer_call = genai_types.FunctionCall(name="transfer_to_agent", args={"agent_name": "review_pipeline"})
    mock_response = _create_mock_response(function_call=mock_transfer_call)

    # We need to mock the underlying genai client's generate_content
    with patch("google.genai.Client") as mock_client_class:
        mock_client = mock_client_class.return_value
        # Mock both sync and async paths just in case
        mock_client.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        runner = Runner(
            agent=root_agent,
            app_name="agent_guardian",
            session_service=mock_session_service,
        )

        # 3. Run the agent with a GitHub URL
        query = "Review this repo: https://github.com/google/adk"

        # We only need to check the FIRST event to see if it triggers the pipeline
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=query)]),
        ):
            events.append(event)
            # Stop after we see the transfer action
            if event.actions and event.actions.transfer_to_agent:
                break

        # 4. Assertions
        assert any(e.actions and e.actions.transfer_to_agent == "review_pipeline" for e in events)

        # Verify the state was updated with user_request
        session = await mock_session_service.get_session(
            app_name="agent_guardian", user_id=user_id, session_id=session_id
        )
        assert session.state["user_request"] == query


@pytest.mark.asyncio
async def test_root_agent_no_delegation_on_greeting(mock_session_service):
    """Verify that root_agent does NOT delegate for simple greetings."""

    user_id = "user_123"
    session_id = "session_789"
    await mock_session_service.create_session(app_name="agent_guardian", user_id=user_id, session_id=session_id)

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
            usage_metadata=genai_types.UsageMetadata(
                prompt_token_count=10, response_token_count=10, total_token_count=20
            ),
        )

    # Mock LLM to return a simple text greeting
    mock_response = _create_mock_response(text="Hello! How can I help you today?")

    with patch("google.genai.Client") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        runner = Runner(
            agent=root_agent,
            app_name="agent_guardian",
            session_service=mock_session_service,
        )

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text="Hi")]),
        ):
            if event.is_final_response() and event.content:
                assert "Hello" in event.content.parts[0].text

        # Verify NO transfer occurred
        session = await mock_session_service.get_session(
            app_name="agent_guardian", user_id=user_id, session_id=session_id
        )
        assert "_transfer_to_agent" not in session.state  # Internal ADK state for transfers
