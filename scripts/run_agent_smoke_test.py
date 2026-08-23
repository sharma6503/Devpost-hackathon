import asyncio
import os
import logging
from dotenv import load_dotenv

# Enable verbose debug logging
logging.basicConfig(level=logging.DEBUG)

import sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

from google.adk.runners import Runner
from agent_guardian.utils.session_factory import get_session_service
from agent_guardian.agent import app
from google.genai import types as genai_types

async def main():
    """Runs the agent with a sample query."""
    print("Initializing session service...")
    session_service = get_session_service()
    await session_service.create_session(
        app_name="agent_guardian", user_id="test_user", session_id="test_session"
    )
    print("Initializing runner...")
    runner = Runner(
        app=app, app_name="agent_guardian", session_service=session_service
    )

    query = "Run a full ADK architecture review on this snippet using the official ADK docs: 'agent = Agent(name=\"test\")'"
    print(f"Sending query: {query}")

    try:
        async for event in runner.run_async(
            user_id="test_user",
            session_id="test_session",
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=query)]
            ),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent: {part.text}")
            if event.error_message:
                print(f"Error: {event.error_message}")
    except Exception as e:
        print(f"Exception during run: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
