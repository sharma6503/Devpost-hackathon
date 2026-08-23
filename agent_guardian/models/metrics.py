from __future__ import annotations

"""
agent_guardian/models/metrics.py

Pydantic schemas for the metrics_agent structured output.

These models define the shape of the review_metrics state key,
which is produced by metrics_agent and consumed by html_agent
and synthesis_agent for scoring and visualization.
"""

from pydantic import BaseModel, Field


class SeverityCounts(BaseModel):
    """Issue counts broken down by severity level."""

    critical: int = Field(default=0, ge=0, description="Count of Critical severity findings.")
    high: int = Field(default=0, ge=0, description="Count of High severity findings.")
    medium: int = Field(default=0, ge=0, description="Count of Medium severity findings.")
    low: int = Field(default=0, ge=0, description="Count of Low severity findings.")

    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.low


class CategoryCounts(BaseModel):
    """Issue counts broken down by review domain."""

    adk: int = Field(default=0, ge=0, description="ADK / Architecture findings.")
    quality: int = Field(default=0, ge=0, description="Code quality findings.")
    security: int = Field(default=0, ge=0, description="Security & deployment findings.")
    validation: int = Field(default=0, ge=0, description="Code execution validation findings.")
    governance: int = Field(default=0, ge=0, description="Governance & compliance findings.")


class DomainScores(BaseModel):
    """Health scores (0–100) for each review domain."""

    security: int = Field(default=0, ge=0, le=100, description="Security posture score.")
    quality: int = Field(default=0, ge=0, le=100, description="Code quality score.")
    architecture: int = Field(default=0, ge=0, le=100, description="ADK architecture score.")
    governance: int = Field(default=0, ge=0, le=100, description="Governance compliance score.")
    validation: int = Field(default=0, ge=0, le=100, description="Code execution validation score.")
    overall: int = Field(default=0, ge=0, le=100, description="Average of all domain scores.")


class ReviewMetrics(BaseModel):
    """
    Top-level structured output for the metrics_agent.

    Written to state['review_metrics']. Consumed by html_agent
    for the visual health scorecard and by synthesis_agent for
    the executive summary table.
    """

    severity: SeverityCounts = Field(
        default_factory=SeverityCounts,
        description="Issue counts by severity.",
    )
    category: CategoryCounts = Field(
        default_factory=CategoryCounts,
        description="Issue counts by review domain.",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Total number of findings across all domains.",
    )
    scores: DomainScores = Field(
        default_factory=DomainScores,
        description="Health scores per domain and overall.",
    )
