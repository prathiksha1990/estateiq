from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_id: str
    category: str
    question: str
    expected_behavior: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_metrics: list[str] = Field(default_factory=list)
    expected_locations: list[str] = Field(default_factory=list)
    conversation_group: str | None = None
    failure_injection: str | None = None


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relevance_score: int = Field(ge=1, le=5)
    groundedness_score: int = Field(ge=1, le=5)
    clarity_score: int = Field(ge=1, le=5)
    overstatement_score: int = Field(ge=1, le=5, description="5 means no overstatement; 1 means severe overstatement")
    passed: bool
    rationale: str


class CheckResult(BaseModel):
    status: str
    detail: str
    evidence: dict[str, Any] = Field(default_factory=dict)
