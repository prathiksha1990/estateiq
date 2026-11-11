import json
import sqlite3
from pathlib import Path

import pandas as pd

from real_estate.database import SCHEMA
from real_estate.evaluation.deterministic import numerical_accuracy, run_checks
from real_estate.evaluation.models import EvaluationCase
from real_estate.evaluation.reporting import generate_reports
from real_estate.evaluation.runner import classify_outcome, dataset_snapshot, inject_failure, load_cases


def make_db(tmp_path):
    path = tmp_path / "evaluation.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.executemany("""INSERT INTO metrics
          (region_id,region_name,state,geography,date,metric_name,value,unit,source_filename,metadata_json)
          VALUES(?,?,?,?,?,?,?,?,?,?)""", [
            ("1", "Alpha", "NJ", "city", "2020-01-31", "zhvi", 100.0, "USD", "fixture.csv", "{}"),
            ("1", "Alpha", "NJ", "city", "2024-01-31", "zhvi", 150.0, "USD", "fixture.csv", "{}"),
            ("1", "Alpha", "NJ", "city", "2025-01-31", "zhvi", 165.0, "USD", "fixture.csv", "{}"),
        ])
    return path


def test_loads_fifteen_real_cases():
    path = Path(__file__).resolve().parents[1] / "evaluation" / "test_cases.csv"
    cases = load_cases(path)
    assert len(cases) == 15
    assert len({case.test_id for case in cases}) == 15
    assert any(case.conversation_group for case in cases)
    assert any(case.failure_injection for case in cases)


def test_dataset_snapshot_is_reproducible(tmp_path):
    path = make_db(tmp_path)
    first, second = dataset_snapshot(path), dataset_snapshot(path)
    assert first == second
    assert first["dataset_rows"] == 3
    assert first["dataset_latest_observation"] == "2025-01-31"


def test_independent_numerical_reconciliation(tmp_path):
    path = make_db(tmp_path)
    state = {"final_answer": "Alpha's home value was $165.00 with 10.00% one-year and 65.00% five-year appreciation.",
             "analysis": {"results": [{"tool": "calculate_appreciation", "metric": "zhvi_appreciation",
                "geography": "city", "records": [{"region_name": "Alpha", "as_of_date": "2025-01-31",
                "latest_value": 165.0, "one_year_pct": 10.0, "five_year_pct": 65.0}]}]}}
    result = numerical_accuracy(path, state)
    assert result.status == "passed"
    state["final_answer"] = "Alpha was $999.00."
    assert numerical_accuracy(path, state).status == "failed"


def test_numerical_reconciliation_rejects_wrong_date_and_direction(tmp_path):
    path = make_db(tmp_path)
    state = {"final_answer": "Alpha was $165.00 on 2024-12-31 and fell 10% over one year.",
             "analysis": {"results": [{"tool": "calculate_appreciation", "metric": "zhvi_appreciation",
                "geography": "city", "records": [{"region_name": "Alpha", "as_of_date": "2025-01-31",
                "latest_value": 165.0, "one_year_pct": 10.0, "five_year_pct": 65.0}]}]}}
    result = numerical_accuracy(path, state)
    assert result.status == "failed"
    assert result.evidence["invalid_date_claims"] == ["2024-12-31"]
    assert result.evidence["direction_errors"] == ["10"]


def test_checks_unsupported_behavior(tmp_path):
    path = make_db(tmp_path)
    case = EvaluationCase(test_id="X", category="unsupported", question="Missing?",
                          expected_behavior="unavailable", expected_tools=["get_latest_market_metric"],
                          expected_metrics=["zhvi"], expected_locations=["Missing"])
    state = {"plan": {"towns": ["Missing"]}, "context_towns": ["Missing"],
             "analysis": {"results": [{"tool": "get_latest_market_metric", "status": "unavailable",
                                        "metric": "zhvi", "records": []}]},
             "final_answer": "No matching observation is available."}
    checks = run_checks(path, case, state)
    assert all(check.status in {"passed", "not_evaluated"} for check in checks.values())


def test_tool_selection_accepts_declared_alternative(tmp_path):
    path = make_db(tmp_path)
    case = EvaluationCase(test_id="X", category="comparison", question="Compare",
                          expected_behavior="success",
                          expected_tools=["compare_markets|calculate_appreciation"])
    state = {"analysis": {"results": [{"tool": "calculate_appreciation", "status": "ok"}]},
             "final_answer": "Supported answer"}
    assert run_checks(path, case, state)["tool_selection"].status == "passed"


def test_failure_injection_restores_tool():
    class Toolkit:
        def latest(self): return "ok"
    class System:
        toolkit = Toolkit()
    original = System.toolkit.latest
    try:
        with inject_failure(System, "latest"):
            try: System.toolkit.latest()
            except sqlite3.OperationalError: pass
            else: raise AssertionError("failure was not injected")
            assert System.toolkit.latest() == "ok"
    finally:
        assert System.toolkit.latest() == original()


def test_report_generation_uses_executed_results(tmp_path):
    frame = pd.DataFrame([{
        "test_id": "E01", "category": "single", "question": "Question", "overall_pass": True,
        "tool_selection_status": "passed", "numerical_accuracy_status": "passed",
        "behavior_status": "passed", "workflow_completion_status": "passed", "failure_injection": "",
        "judge_relevance_score": 5, "judge_groundedness_score": 5, "latency_seconds": 1.2,
        "failed_checks": "", "workflow_error": "", "judge_rationale": "Grounded", "final_answer": "Answer",
    }])
    metadata = {"run_id": "test-run", "execution_timestamp": "2026-01-01T00:00:00Z",
                "model": "mock", "dataset_sha256": "abc", "dataset_latest_observation": "2025-01-31"}
    generate_reports(frame, metadata, tmp_path)
    report = (tmp_path / "evaluation_report.md").read_text()
    assert "Tests executed: **1**" in report
    assert "Passed: **1**" in report
    assert (tmp_path / "failure_analysis.md").is_file()


def test_outcomes_separate_recovery_from_graceful_error(tmp_path):
    case = EvaluationCase(test_id="X", category="failure", question="Q", expected_behavior="success",
                          failure_injection="latest")
    checks = {}
    recovered = {"execution_retry_count": 1, "final_answer": "Recovered",
                 "analysis": {"results": [{"status": "ok"}]}}
    assert classify_outcome(case, recovered, True, checks, None)[0] == "successful_recovery"
    errored = {"execution_retry_count": 0, "final_answer": "Could not retrieve",
               "analysis": {"results": [{"status": "error"}]}}
    assert classify_outcome(case, errored, False, checks, None)[0] == "graceful_error_reporting"


def test_judge_failure_is_excluded_not_counted_as_agent_failure():
    case = EvaluationCase(test_id="X", category="single", question="Q", expected_behavior="success")
    outcome, reason = classify_outcome(case, {"final_answer": "Answer"}, False, {}, "quota")
    assert outcome == "not_scored"
    assert "quota" in reason
