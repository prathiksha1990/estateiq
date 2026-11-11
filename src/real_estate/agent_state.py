from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    clarification_response: str
    plan: dict[str, Any]
    analysis: dict[str, Any]
    report: dict[str, Any]
    validation: dict[str, Any]
    deterministic_validation: dict[str, Any]
    final_answer: str
    terminal_answer: str | None
    retry_count: int
    execution_retry_count: int
    context_towns: list[str]
    context_metrics: list[str]
    context_geography: str | None
    error: str | None

