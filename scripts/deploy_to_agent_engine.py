import os
import vertexai
from vertexai import types
from vertexai.preview import reasoning_engines
from agent_guardian.agent import root_agent
from dotenv import load_dotenv
from google.adk.plugins.logging_plugin import LoggingPlugin
from agent_guardian.utils.token_utils import TokenSafetyPlugin
from google.adk.plugins import ReflectAndRetryToolPlugin
from agent_guardian.config import Config

configs = Config()


# Load environment variables from .env
load_dotenv()

# --- Configuration ---

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
# Reasoning Engine deployment needs a regional endpoint (e.g., us-central1).
if LOCATION == "global":
    LOCATION = "us-central1"

STAGING_BUCKET = os.environ.get("STAGING_BUCKET")
if not STAGING_BUCKET:
    STAGING_BUCKET = "gs://agentgaurdian"

DISPLAY_NAME = "Agent Guardian"
DESCRIPTION = "Agent Guardian — Multi-Agent Audit Orchestrator for Codebase Reviews"

# If provided, update this instance instead of creating a new one
# Example: projects/815653336269/locations/us-central1/reasoningEngines/6839756721917788160
INSTANCE_RESOURCE_NAME = os.environ.get("REASONING_ENGINE_RESOURCE_NAME")

# List of environment variables to forward to the remote engine
ENV_VARS_TO_FORWARD = [
    "GOOGLE_GENAI_USE_VERTEXAI",
    # "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    # "GITHUB_TOKEN",
    # "GITHUB_REMEDIATION_REPO",
    # "GITHUB_BASE_BRANCH",
    "ATLASSIAN_URL",
    "ATLASSIAN_USERNAME",
    "ATLASSIAN_API_TOKEN",
    "ATLASSIAN_CLOUD_ID",
    "CONFLUENCE_PAGE_URLS",
    "EVAL_PASS_THRESHOLD",
    "EVAL_MAX_ITERATIONS",
    "ARTIFACT_SERVICE_URI",
    "ARTIFACT_BUCKET",
    # System & Cloud Trace Telemetry Config (Google Cloud Trace via OpenTelemetry)
    "NPM_CONFIG_CACHE",
    "UV_CACHE_DIR",
    "PYTHONUNBUFFERED",
    "ENABLE_CLOUD_TRACING",
    "OTEL_TO_CLOUD",
    "OTEL_SERVICE_NAME",
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY",
    "OTEL_SEMCONV_STABILITY_OPT_IN",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS",
]

# --- End Configuration ---

def deploy():
    if not PROJECT_ID:
        print("Error: GOOGLE_CLOUD_PROJECT environment variable is not set.")
        return

    print(f"Initializing Vertex AI Client with project={PROJECT_ID}, location={LOCATION}")
    client = vertexai.Client(project=PROJECT_ID, location=LOCATION)

    print("Wrapping ADK root_agent with AdkApp...")
    # AdkApp handles ADK-to-ReasoningEngine conversion
    app = reasoning_engines.AdkApp(
        agent=root_agent,
        plugins=[
            LoggingPlugin(),
            ReflectAndRetryToolPlugin(max_retries=configs.max_retries),
            TokenSafetyPlugin(),
        ],
        enable_tracing=True,
    )

    # Collect env vars from current environment
    env_vars = {var: os.environ.get(var) for var in ENV_VARS_TO_FORWARD if os.environ.get(var)}

    # Ensure Cloud Trace and telemetry are enabled in Agent Engine
    env_vars.setdefault("ENABLE_CLOUD_TRACING", "true")
    env_vars.setdefault("GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", "true")
    env_vars.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_agent_spans")
    env_vars.setdefault("OTEL_SERVICE_NAME", "agent-guardian")

    # Set default caches to /tmp for managed runtime stability (aligned with Dockerfile)
    env_vars.setdefault("NPM_CONFIG_CACHE", "/tmp/.npm")
    env_vars.setdefault("UV_CACHE_DIR", "/tmp/.uv_cache")
    env_vars.setdefault("PYTHONUNBUFFERED", "1")

    # Ensure binaries installed via setup script (uv, node) are in PATH
    # Use a standard Linux PATH; do NOT append the local Windows PATH
    env_vars.setdefault("PATH", "/usr/local/bin:/usr/sbin:/sbin:/usr/bin:/bin")

    print("Creating Reasoning Engine instance with vertexai.Client...")
    # Requirements from pyproject.toml
    # Pinned to the exact version in uv.lock — the agent code uses ADK 2.x
    # graph Workflow/App APIs that do not exist in 1.x.
    requirements = [
        "google-adk==2.5.0",
        "httpx>=0.28",
        "google-cloud-aiplatform", # Required for vertexai module during unpickling
        "google-genai",
        "cloudpickle",
        "mcp>=1.0.0",
        "python-dotenv",
        "pydantic>=2.0.0",
        "beautifulsoup4",
        "requests",
        "distro",
        "fastapi",
        "gradio",
        "markdown",
        "markdownify",
        "uvicorn",
        "opentelemetry-exporter-gcp-trace",
        "opentelemetry-exporter-otlp-proto-http",
        "google-cloud-trace",
    ]

    print("Defining class methods for Agent Engine...")
    # These methods align with AdkApp's exposed operations
    class_methods = [
        {"name": "get_session", "api_mode": ""},
        {"name": "list_sessions", "api_mode": ""},
        {"name": "create_session", "api_mode": ""},

        {"name": "delete_session", "api_mode": ""},
        {"name": "async_get_session", "api_mode": "async"},
        {"name": "async_list_sessions", "api_mode": "async"},
        {"name": "async_create_session", "api_mode": "async"},
        {"name": "async_delete_session", "api_mode": "async"},
        {"name": "async_add_session_to_memory", "api_mode": "async"},
        {"name": "async_search_memory", "api_mode": "async"},
        {"name": "stream_query", "api_mode": "stream"},
        {"name": "streaming_agent_run_with_events", "api_mode": "stream"},
        {"name": "async_stream_query", "api_mode": "async_stream"},
        {"name": "bidi_stream_query", "api_mode": "bidi_stream"},
    ]

    config = {
        "display_name": DISPLAY_NAME,
        "description": DESCRIPTION,
        "staging_bucket": STAGING_BUCKET,
        "requirements": requirements,
        "gcs_dir_name":"agentguardian",
        "env_vars": env_vars,
        "python_version": "3.13", # Pin to 3.13 to match Dockerfile and ensure compatibility
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "agent_framework": "google-adk",
        "min_instances": 1,
        "max_instances": 5,
        "labels": {
            "adk_agent_name":"agentguardian"
        },
        "resource_limits": {"cpu": "8", "memory": "32Gi"},
        "container_concurrency": 10,
        "build_options": {
            "installation_scripts": ["installation_scripts/setup_agent_engine.sh"]
        },
        "extra_packages": ["agent_guardian", "installation_scripts/setup_agent_engine.sh"], # Match the script path exactly
        "class_methods": class_methods,
    }

    try:
        if INSTANCE_RESOURCE_NAME:
            print(f"Updating existing Reasoning Engine instance: {INSTANCE_RESOURCE_NAME}")

            # Prepare update config - some fields like python_version might not be updatable
            # We'll include the core fields that are likely to change or are required for the agent update
            update_config = {
                "display_name": DISPLAY_NAME,
                "description": DESCRIPTION,
                "staging_bucket": STAGING_BUCKET,
                "requirements": requirements,
                "env_vars": env_vars,
                "extra_packages": ["agent_guardian", "installation_scripts/setup_agent_engine.sh"],
                "class_methods": class_methods,
                "build_options": {
                    "installation_scripts": ["installation_scripts/setup_agent_engine.sh"]
                },
            }

            # Use the Gen AI SDK client.agent_engines.update method
            remote_app = client.agent_engines.update(
                name=INSTANCE_RESOURCE_NAME,
                agent=app,
                config=update_config
            )
            print("Agent Update Initiated Successfully!")
        else:
            print("Creating NEW Reasoning Engine instance...")
            remote_app = client.agent_engines.create(
                agent=app,
                config=config
            )
            print("Agent Deployed Successfully!")

        print("\n" + "="*50)
        print(f"Resource Name: {remote_app.api_resource.name}")
        print(f"Deployment ID: {remote_app.api_resource.name.split('/')[-1]}")
        print("="*50)

        return remote_app

    except Exception as e:
        print(f"\nDeployment failed: {e}")
        raise

if __name__ == "__main__":
    deploy()
