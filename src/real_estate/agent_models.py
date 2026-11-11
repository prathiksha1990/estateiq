from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchPlan(StrictModel):
    interpreted_question: str
    towns: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    geography: Literal["city", "county", "zip", "msa", "state"] | None = None
    start_date: str | None = None
    end_date: str | None = None
    tools: list[Literal[
        "list_available_metrics", "list_available_locations",
        "get_home_value_trend", "compare_markets",
        "calculate_appreciation", "get_latest_market_metric",
    ]] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_question: str | None = None


class ToolResult(StrictModel):
    tool: str
    status: Literal["ok", "unavailable", "error"]
    source: str = "data/processed/real_estate.db"
    metric: str | None = None
    unit: str | None = None
    geography: str | None = None
    region_ids: list[str] = Field(default_factory=list)
    date_start: str | None = None
    date_end: str | None = None
    missing_observations: int = 0
    records: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class AnalysisBundle(StrictModel):
    question: str
    results: list[ToolResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class MarketReport(StrictModel):
    answer: str
    observations: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ValidationResult(StrictModel):
    valid: bool
    numerical_claims_verified: bool
    geography_verified: bool
    units_and_dates_verified: bool
    answers_question: bool
    errors: list[str] = Field(default_factory=list)
    correction_instructions: str | None = None

