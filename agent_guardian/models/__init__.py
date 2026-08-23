from __future__ import annotations

"""
agent_guardian/models — Pydantic domain models (loose-coupled schema registry)

All structured output schemas used by ADK agents live here.
Import from this package rather than from individual sub-agents.

Usage:
    from agent_guardian.models import EvaluationResult, ReviewScore, ReviewMetrics
"""

from .evaluation import EvaluationResult, ReviewScore
from .metrics import ReviewMetrics, SeverityCounts, CategoryCounts, DomainScores
from .remediation import RemediationPlan, CodeChange
from .planning import ReviewPlan, ExpertAssignment

__all__ = [
    # Evaluation quality gate schemas
    "EvaluationResult",
    "ReviewScore",
    # Review metrics schemas
    "ReviewMetrics",
    "SeverityCounts",
    "CategoryCounts",
    "DomainScores",
    # A2A remediation schemas
    "RemediationPlan",
    "CodeChange",
    # Planning schemas
    "ReviewPlan",
    "ExpertAssignment",
]
