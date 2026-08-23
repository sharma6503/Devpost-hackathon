from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from google.adk.tools.tool_context import ToolContext


@pytest.fixture
def mock_tool_context():
    context = MagicMock(spec=ToolContext)
    context.state = {}
    context.session_id = "test_session_123"
    context.history = []
    context.session = MagicMock()
    context.session.events = []
    return context


@pytest.fixture
def sample_python_code():
    return """
def hello_world():
    print("Hello, world!")

def insecure_function(data):
    # SEC-001: Hardcoded secret
    api_key = "AIzaSyA1234567890"
    return api_key

def no_timeout_call():
    import requests
    return requests.get("https://example.com")
"""


@pytest.fixture
def sample_requirements():
    return """
requests==2.31.0
fastapi
google-adk>=1.31.1
"""
