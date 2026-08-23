import asyncio
import os
import tempfile
import zipfile
import shutil
from dotenv import load_dotenv

# Ensure PYTHONPATH is set so agent_guardian can be imported
import sys

sys.path.append(os.getcwd())

load_dotenv()

# Pre-auth mapping for legacy support
if not os.environ.get("ATLASSIAN_MCP_API_TOKEN"):
    os.environ["ATLASSIAN_MCP_API_TOKEN"] = os.environ.get("ATLASSIAN_API_TOKEN", "")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from agent_guardian.agent import root_agent
from google.genai import types as genai_types


async def main():
    """Runs the agent with a code review query and a packaged ZIP source."""
    print("Initializing temporary ZIP file...")
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, "insecure_function.py")
    with open(file_path, "w") as f:
        f.write("def insecure_function(user_input):\n    eval(user_input)\n    print('Hello ' + user_input)\n")

    zip_path = os.path.join(temp_dir, "codebase.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.write(file_path, arcname="insecure_function.py")
    print(f"Created temporary ZIP file at: {zip_path}")

    print("Initializing session service...")
    session_service = InMemorySessionService()
    await session_service.create_session(app_name="agent_guardian", user_id="test_user", session_id="test_session")

    # Inject the ZIP path into the session state to trigger local parsing workflow
    session = await session_service.get_session(
        app_name="agent_guardian", user_id="test_user", session_id="test_session"
    )
    session.state["uploaded_zip_path"] = zip_path

    print("Initializing runner...")
    runner = Runner(agent=root_agent, app_name="agent_guardian", session_service=session_service)

    # This query triggers the review_pipeline
    query = f"Please review the uploaded code in the ZIP file at {zip_path} for security and quality."
    print(f"Sending query: {query}")
    print("-" * 50)

    try:
        async for event in runner.run_async(
            user_id="test_user",
            session_id="test_session",
            new_message=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=query)]),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        # Print agent output as it streams
                        print(part.text, end="", flush=True)
            if event.error_message:
                print(f"\nError: {event.error_message}")
        print("\n" + "-" * 50)
        print("Run complete.")
    except Exception as e:
        print(f"\nException during run: {e}")
    finally:
        try:
            shutil.rmtree(temp_dir)
            print("Cleaned up temporary ZIP directory.")
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
