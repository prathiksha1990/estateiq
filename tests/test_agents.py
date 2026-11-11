import json
import sqlite3

import pytest

from real_estate.agent_graph import RealEstateAgentSystem
from real_estate.agent_models import MarketReport, ResearchPlan, ValidationResult
from real_estate.database import SCHEMA


class Runner:
    def __init__(self, owner, schema):
        self.owner, self.schema = owner, schema

    def invoke(self, messages):
        self.owner.prompts.setdefault(self.schema, []).append(messages[-1].content)
        queue = self.owner.responses[self.schema]
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class MockLLM:
    def __init__(self, **responses):
        self.responses = {ResearchPlan: list(responses.get("plans", [])),
                          MarketReport: list(responses.get("reports", [])),
                          ValidationResult: list(responses.get("validations", []))}
        self.prompts = {}

    def with_structured_output(self, schema):
        return Runner(self, schema)


def valid():
    return ValidationResult(valid=True, numerical_claims_verified=True, geography_verified=True,
                            units_and_dates_verified=True, answers_question=True)


def report(text="Supported answer"):
    return MarketReport(answer=text, observations=[text], interpretations=[], limitations=[])


def plan(towns, metric="zhvi", geography="city", tools=None):
    return ResearchPlan(interpreted_question="test", towns=towns, metrics=[metric], geography=geography,
                        tools=tools or ["get_latest_market_metric"])


@pytest.fixture
def agent_db(tmp_path):
    path = tmp_path / "agent.db"
    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA)
        rows = [
            ("1", "Alpha", "NJ", "city", "2020-01-31", "zhvi", 100.0, "USD", "fixture.csv", "{}"),
            ("1", "Alpha", "NJ", "city", "2024-01-31", "zhvi", 150.0, "USD", "fixture.csv", "{}"),
            ("1", "Alpha", "NJ", "city", "2025-01-31", "zhvi", 165.0, "USD", "fixture.csv", "{}"),
            ("2", "Beta", "NJ", "city", "2020-01-31", "zhvi", 200.0, "USD", "fixture.csv", "{}"),
            ("2", "Beta", "NJ", "city", "2025-01-31", "zhvi", None, "USD", "fixture.csv", "{}"),
            ("10", "Trenton, NJ", "NJ", "msa", "2025-01-31", "sales_count", 30.0, "sales", "sales.csv", "{}"),
        ]
        con.executemany("""INSERT INTO metrics(region_id,region_name,state,geography,date,metric_name,value,unit,source_filename,metadata_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", rows)
        con.executemany("""INSERT INTO datasets(source_filename,metric_name,description,unit,geography_levels,
                           populated_value_count,date_start,date_end) VALUES(?,?,?,?,?,?,?,?)""", [
            ("fixture.csv", "zhvi", "ZHVI", "USD", '["city"]', 4, "2020-01-31", "2025-01-31"),
            ("sales.csv", "sales_count", "Sales", "sales", '["msa"]', 1, "2025-01-31", "2025-01-31"),
        ])
    return path


def system(agent_db, mock):
    return RealEstateAgentSystem(agent_db, None, mock, mock, mock)


def test_single_town_question_uses_actual_database(agent_db):
    mock = MockLLM(plans=[plan(["Alpha"])], reports=[report("Alpha was 165 USD on 2025-01-31.")], validations=[valid()])
    app = system(agent_db, mock)
    result = app.ask("What is Alpha's latest home value?", "single")
    assert result["final_answer"].startswith("Alpha was 165")
    assert result["analysis"]["results"][0]["records"][0]["value"] == 165.0


def test_structured_planner_retries_transient_provider_failure(agent_db):
    mock = MockLLM(plans=[RuntimeError("invalid structured output"), plan(["Alpha"])],
                   reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("What is Alpha's latest home value?", "provider-retry")
    assert result["final_answer"] == "Supported answer"
    assert len(mock.prompts[ResearchPlan]) == 2


def test_multi_town_comparison_and_missing_data(agent_db):
    p = plan(["Alpha", "Beta"], tools=["compare_markets"])
    mock = MockLLM(plans=[p], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("Compare Alpha and Beta", "multi")
    tool = result["analysis"]["results"][0]
    assert tool["status"] == "ok"
    assert tool["missing_observations"] == 1
    summaries = [x for x in tool["calculations"] if x["calculation"] == "region_change"]
    assert {x["region_name"] for x in summaries} == {"Alpha", "Beta"}


def test_multi_metric_plan_executes_every_metric(agent_db):
    p = ResearchPlan(interpreted_question="compare", towns=["Trenton, NJ"],
                     metrics=["sales_count", "median_sale_price"], geography="msa",
                     tools=["get_latest_market_metric"])
    mock = MockLLM(plans=[p], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("Compare sales and sale price in Trenton", "multi-metric")
    assert [item["metric"] for item in result["analysis"]["results"]] == ["sales_count", "median_sale_price"]
    assert [item["status"] for item in result["analysis"]["results"]] == ["ok", "unavailable"]
    assert result["analysis"]["results"][0]["region_ids"] == ["10"]
    assert "not available" in result["analysis"]["results"][1]["message"]


def test_named_msa_is_recovered_when_planner_omits_towns(agent_db):
    p = ResearchPlan(interpreted_question="latest sales", towns=[], metrics=["sales_count"],
                     geography="msa", tools=["get_latest_market_metric"])
    mock = MockLLM(plans=[p], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("Latest sales in the Trenton NJ metro", "recover-location")
    assert result["plan"]["towns"] == ["Trenton, NJ"]
    assert {row["region_name"] for row in result["analysis"]["results"][0]["records"]} == {"Trenton, NJ"}


def test_follow_up_preserves_prior_context(agent_db):
    mock = MockLLM(plans=[plan(["Alpha"]), plan(["Alpha", "Beta"], tools=["compare_markets"])],
                   reports=[report(), report()], validations=[valid(), valid()])
    app = system(agent_db, mock)
    app.ask("Tell me about Alpha", "conversation")
    second = app.ask("How does that compare with Beta?", "conversation")
    planner_payload = json.loads(mock.prompts[ResearchPlan][1])
    assert planner_payload["previous_context"]["towns"] == ["Alpha"]
    assert second["context_towns"] == ["Alpha", "Beta"]


def test_unsupported_metric_or_geography_is_not_substituted(agent_db):
    mock = MockLLM(plans=[plan(["Alpha"], "sales_count", "city")], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("Alpha city sales?", "unsupported")
    assert result["analysis"]["results"][0]["status"] == "unavailable"
    assert result["analysis"]["results"][0]["metric"] == "sales_count"


def test_unsupported_county_geography_is_explicit(agent_db):
    mock = MockLLM(plans=[plan(["Alpha"], "zhvi", "county")], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("Alpha county home values?", "unsupported-county")
    tool = result["analysis"]["results"][0]
    assert tool["status"] == "unavailable"
    assert "county" in tool["message"]
    assert "supported geography: city" in tool["message"]


def test_invalid_geographic_name_returns_unavailable(agent_db):
    mock = MockLLM(plans=[plan(["Not A Town"])], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask("Latest value in Not A Town", "invalid")
    assert result["analysis"]["results"][0]["status"] == "unavailable"


def test_explicit_unsupported_location_is_terminal_without_llm(agent_db):
    mock = MockLLM()
    result = system(agent_db, mock).ask("Latest home value in Atlantis New Jersey", "invalid-preflight")
    assert "not available" in result["final_answer"].casefold()
    assert result["context_towns"] == ["Atlantis"]


def test_clarification_interrupt_and_resume(agent_db):
    clarification = ResearchPlan(interpreted_question="ambiguous", requires_clarification=True,
                                 clarification_question="Which New Jersey town?")
    mock = MockLLM(plans=[clarification, plan(["Alpha"])], reports=[report()], validations=[valid()])
    app = system(agent_db, mock)
    paused = app.ask("What is the market like?", "clarify")
    assert paused["__interrupt__"][0].value["type"] == "clarification"
    done = app.resume("Alpha", "clarify")
    assert done["final_answer"] == "Supported answer"


def test_duplicate_place_name_requests_region_id_clarification(agent_db):
    with sqlite3.connect(agent_db) as con:
        con.executemany("""INSERT INTO metrics(region_id,region_name,state,geography,date,metric_name,value,unit,source_filename,metadata_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", [
            ("20", "Springfield", "NJ", "city", "2025-01-31", "zhvi", 200.0, "USD", "fixture.csv", "{}"),
            ("21", "Springfield", "NJ", "city", "2025-01-31", "zhvi", 220.0, "USD", "fixture.csv", "{}"),
        ])
    mock = MockLLM(plans=[plan(["Springfield"])])
    result = system(agent_db, mock).ask("Latest Springfield value", "duplicate-place")
    prompt = result["__interrupt__"][0].value["question"]
    assert "Zillow region ID" in prompt
    assert "20" in prompt and "21" in prompt


def test_unsupported_metric_clarification_becomes_terminal_unavailable(agent_db):
    p = ResearchPlan(interpreted_question="unsupported", geography="city", requires_clarification=True,
                     clarification_question="This metric is not currently available. What did you mean?")
    mock = MockLLM(plans=[p])
    result = system(agent_db, mock).ask("What is Alpha's price-cut share?", "unsupported-terminal")
    assert "not available" in result["final_answer"].casefold()
    assert "__interrupt__" not in result


def test_property_level_valuation_is_refused_without_tools(agent_db):
    mock = MockLLM(plans=[plan(["Alpha"])])
    result = system(agent_db, mock).ask("Is 123 Main Street in Alpha undervalued?", "property-refusal")
    assert "cannot determine" in result["final_answer"].casefold()
    assert result["analysis"] == {}


def test_statewide_multi_metric_request_requires_clarification(agent_db):
    p = ResearchPlan(interpreted_question="state market", towns=[],
                     metrics=["zhvi", "sales_count"], geography="msa",
                     tools=["get_latest_market_metric"])
    mock = MockLLM(plans=[p])
    result = system(agent_db, mock).ask("How is the New Jersey housing market doing?", "statewide")
    assert result["__interrupt__"][0].value["type"] == "clarification"


def test_latest_appreciation_does_not_require_time_period_clarification(agent_db):
    p = ResearchPlan(interpreted_question="comparison", towns=["Alpha", "Beta"],
                     metrics=["zhvi"], geography="city", tools=["compare_markets"],
                     requires_clarification=True,
                     clarification_question="Which time period would you like for the appreciation calculation?")
    mock = MockLLM(plans=[p], reports=[report()], validations=[valid()])
    result = system(agent_db, mock).ask(
        "Compare Alpha and Beta on latest home values and appreciation.", "period-default")
    assert "__interrupt__" not in result
    assert result["analysis"]["results"][0]["tool"] == "compare_markets"


def test_tool_failure_is_reported(agent_db, monkeypatch):
    mock = MockLLM(plans=[plan(["Alpha"])])
    app = system(agent_db, mock)
    monkeypatch.setattr(app.toolkit, "latest", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("broken")))
    result = app.ask("Latest Alpha value", "failure")
    assert "could not retrieve" in result["final_answer"].casefold()
    assert result["execution_retry_count"] == 0


def test_transient_database_failure_is_retried(agent_db, monkeypatch):
    mock = MockLLM(plans=[plan(["Alpha"])], reports=[report()], validations=[valid()])
    app = system(agent_db, mock)
    original = app.toolkit.latest
    calls = 0
    def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("temporary")
        return original(*args, **kwargs)
    monkeypatch.setattr(app.toolkit, "latest", flaky)
    result = app.ask("Latest Alpha value", "transient")
    assert result["execution_retry_count"] == 1
    assert result["analysis"]["results"][0]["status"] == "ok"


def test_permanent_database_failure_is_not_retried(agent_db, monkeypatch):
    mock = MockLLM(plans=[plan(["Alpha"])])
    app = system(agent_db, mock)
    calls = 0
    def broken(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise sqlite3.IntegrityError("permanent")
    monkeypatch.setattr(app.toolkit, "latest", broken)
    result = app.ask("Latest Alpha value", "permanent")
    assert calls == 1
    assert result["execution_retry_count"] == 0
    assert "after 1 attempt" in result["final_answer"]


def test_validation_retries_at_most_twice(agent_db):
    invalid = ValidationResult(valid=False, numerical_claims_verified=False, geography_verified=True,
                               units_and_dates_verified=False, answers_question=True,
                               errors=["wrong number"], correction_instructions="Use the retrieved value.")
    mock = MockLLM(plans=[plan(["Alpha"])], reports=[report("wrong"), report("correct")],
                   validations=[invalid, valid()])
    result = system(agent_db, mock).ask("Latest Alpha value", "retry")
    assert result["final_answer"] == "correct"
    assert result["retry_count"] == 1
    assert len(mock.prompts[MarketReport]) == 2

