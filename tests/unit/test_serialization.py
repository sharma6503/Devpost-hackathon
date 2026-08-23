import json
import pickle
from google.adk.tools import FunctionTool

from agent_guardian.agent import app, root_agent
from agent_guardian.state import ReviewState
from agent_guardian.models import (
    EvaluationResult,
    ReviewScore,
    ReviewMetrics,
    SeverityCounts,
    CategoryCounts,
    DomainScores,
    RemediationPlan,
    CodeChange,
    ReviewPlan,
    ExpertAssignment,
)
from agent_guardian.utils.loop_state import LoopState
import agent_guardian.tools as tools_pkg


def test_models_json_and_pickle_serialization():
    """Verify all Pydantic models and state dataclasses serialize to JSON and pickle cleanly."""
    models = [
        ReviewState(),
        EvaluationResult(
            scores=[ReviewScore(agent="security_expert", specificity=9, evidence=8, actionability=8, avg=8.33)],
            overall_score=8.5,
            passed=True,
            feedback="Passed quality gate",
            critical_issues=[],
        ),
        ReviewMetrics(
            severity=SeverityCounts(critical=0, high=1, medium=2, low=3, info=4),
            categories=CategoryCounts(),
            scores=DomainScores(overall=85.0),
        ),
        RemediationPlan(
            target_repo="owner/repo",
            base_branch="main",
            pr_branch="guardian/fix-1",
            pr_title="Fix findings",
            pr_body="Automated fixes",
            priority="high",
            estimated_risk="low",
            changes=[
                CodeChange(
                    file_path="app.py",
                    action="modify",
                    description="fix",
                    old_content_pattern="foo",
                    new_content="bar",
                )
            ],
        ),
        ReviewPlan(
            is_large_codebase=False,
            total_files=10,
            assignments=[
                ExpertAssignment(expert_name="security_expert", assigned_modules=["auth.py"], reason="Auth review")
            ],
        ),
        LoopState(iterations=1, exit_requested=False, exit_reason="", parse_failures=0),
    ]

    for model in models:
        # 1. Pickle roundtrip
        pickled = pickle.dumps(model)
        assert len(pickled) > 0
        unpickled = pickle.loads(pickled)
        assert type(unpickled) is type(model)

        # 2. JSON serialization
        if hasattr(model, "model_dump_json"):
            json_str = model.model_dump_json()
            assert isinstance(json_str, str)
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)


def _clean_mocks(obj, visited=None):
    if visited is None:
        visited = set()
    obj_id = id(obj)
    if obj_id in visited:
        return
    visited.add(obj_id)
    from unittest.mock import NonCallableMock

    if hasattr(obj, "__dict__") and isinstance(obj.__dict__, dict):
        for k, v in list(obj.__dict__.items()):
            if isinstance(v, NonCallableMock):
                setattr(obj, k, None)
            else:
                _clean_mocks(v, visited)
    if hasattr(obj, "__pydantic_private__") and isinstance(obj.__pydantic_private__, dict):
        for k, v in list(obj.__pydantic_private__.items()):
            if isinstance(v, NonCallableMock):
                obj.__pydantic_private__[k] = None
            else:
                _clean_mocks(v, visited)
    if isinstance(obj, (list, tuple)):
        for item in obj:
            _clean_mocks(item, visited)
    elif isinstance(obj, dict):
        for v in obj.values():
            _clean_mocks(v, visited)


def test_root_agent_and_app_pickling():
    """Verify root_agent and App serialize cleanly with pickle (required for Vertex AI Agent Engine & session stores)."""
    _clean_mocks(root_agent)
    _clean_mocks(app)

    # Pickling root_agent
    pickled_root = pickle.dumps(root_agent)
    assert len(pickled_root) > 0
    unpickled_root = pickle.loads(pickled_root)
    assert unpickled_root.name == root_agent.name

    # Pickling ADK app
    pickled_app = pickle.dumps(app)
    assert len(pickled_app) > 0
    unpickled_app = pickle.loads(pickled_app)
    assert unpickled_app.root_agent.name == app.root_agent.name


def test_all_tools_declaration_schema_generation():
    """Verify all tool functions in agent_guardian.tools can generate valid declarations."""
    for tool_name in tools_pkg.__all__:
        func = getattr(tools_pkg, tool_name)
        tool = FunctionTool(func=func)
        decl = tool._get_declaration()
        assert decl is not None
        assert decl.name is not None
