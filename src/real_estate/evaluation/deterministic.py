import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from .models import CheckResult, EvaluationCase
from ..claim_validation import validate_numerical_claims


def _norm(value: str) -> str:
    return value.casefold().replace(" metro", "").strip()


def tool_selection(case: EvaluationCase, state: dict) -> CheckResult:
    actual = {r.get("tool") for r in state.get("analysis", {}).get("results", [])}
    missing = sorted(expectation for expectation in case.expected_tools
                     if not any(option in actual for option in expectation.split("|")))
    return CheckResult(status="passed" if not missing else "failed",
                       detail="All required tools executed." if not missing else f"Missing tools: {missing}",
                       evidence={"expected": case.expected_tools, "actual": sorted(x for x in actual if x)})


def location_coverage(case: EvaluationCase, state: dict) -> CheckResult:
    actual = set(state.get("context_towns", []))
    for result in state.get("analysis", {}).get("results", []):
        actual.update(r.get("region_name") for r in result.get("records", []) if r.get("region_name"))
    missing = [x for x in case.expected_locations if _norm(x) not in {_norm(a) for a in actual}]
    # An unsupported location is correctly covered when the plan retained its name.
    if case.expected_behavior == "unavailable":
        actual.update(state.get("plan", {}).get("towns", []))
        missing = [x for x in case.expected_locations if _norm(x) not in {_norm(a) for a in actual}]
    return CheckResult(status="passed" if not missing else "failed",
                       detail="Required locations covered." if not missing else f"Missing locations: {missing}",
                       evidence={"expected": case.expected_locations, "actual": sorted(actual)})


def metric_coverage(case: EvaluationCase, state: dict) -> CheckResult:
    actual = set()
    for result in state.get("analysis", {}).get("results", []):
        metric = result.get("metric")
        if metric == "zhvi_appreciation": metric = "zhvi"
        if metric: actual.add(metric)
    missing = sorted(set(case.expected_metrics) - actual)
    return CheckResult(status="passed" if not missing else "failed",
                       detail="Required metrics covered." if not missing else f"Missing metrics: {missing}",
                       evidence={"expected": case.expected_metrics, "actual": sorted(actual)})


def behavior(case: EvaluationCase, state: dict) -> CheckResult:
    answer = state.get("final_answer", "") or ""
    results = state.get("analysis", {}).get("results", [])
    statuses = {r.get("status") for r in results}
    interrupted = bool(state.get("__interrupt__"))
    expected = case.expected_behavior
    if expected == "success": ok = bool(answer) and not state.get("error") and "ok" in statuses
    elif expected in {"unavailable", "insufficient_data"}:
        ok = "unavailable" in statuses or any(term in answer.casefold() for term in
            ("not available", "unavailable", "insufficient", "no matching", "does not contain", "no value can be reported"))
    elif expected == "clarification": ok = interrupted
    elif expected == "graceful_error": ok = bool(state.get("error")) and bool(answer)
    elif expected == "refuse_property_valuation":
        ok = any(term in answer.casefold() for term in ("cannot determine", "can't determine", "not a property", "property-level", "undervalued"))
    else: ok = False
    return CheckResult(status="passed" if ok else "failed", detail=f"Expected behavior: {expected}.",
                       evidence={"result_statuses": sorted(x for x in statuses if x), "interrupted": interrupted,
                                 "error": state.get("error")})


def workflow_completion(case: EvaluationCase, state: dict) -> CheckResult:
    completed = ((bool(state.get("final_answer")) and not state.get("error")) or
                 (case.expected_behavior == "clarification" and bool(state.get("__interrupt__"))))
    return CheckResult(status="passed" if completed else "failed",
                       detail="Workflow reached an answer or expected interrupt." if completed else "No terminal answer or expected interrupt.")


def _db_value(connection, region: str, metric: str, geography: str, observation_date: str):
    row = connection.execute("""SELECT value, unit FROM metrics WHERE region_name=? COLLATE NOCASE
                              AND metric_name=? AND geography=? AND date=?""",
                             (region, metric, geography, observation_date[:10])).fetchone()
    return row


def _independent_appreciation(connection, region: str, years: int):
    rows = connection.execute("""SELECT date, value FROM metrics WHERE region_name=? COLLATE NOCASE
                               AND metric_name='zhvi' AND geography='city' AND value IS NOT NULL ORDER BY date""",
                              (region,)).fetchall()
    if not rows: return None
    latest_date, latest_value = rows[-1]
    latest = date.fromisoformat(latest_date)
    try: target = latest.replace(year=latest.year - years)
    except ValueError: target = latest.replace(year=latest.year - years, day=28)
    candidates = [(d, v) for d, v in rows if date.fromisoformat(d) <= target]
    if not candidates or candidates[-1][1] == 0: return None
    return (latest_value / candidates[-1][1] - 1) * 100


def _independent_change(connection, region: str, metric: str, geography: str, years: int):
    rows = connection.execute("""SELECT date, value FROM metrics WHERE region_name=? COLLATE NOCASE
                              AND metric_name=? AND geography=? AND value IS NOT NULL ORDER BY date""",
                              (region, metric, geography)).fetchall()
    if not rows:
        return None
    latest_date, latest_value = rows[-1]
    latest = date.fromisoformat(latest_date)
    try: target = latest.replace(year=latest.year - years)
    except ValueError: target = latest.replace(year=latest.year - years, day=28)
    candidates = [(d, v) for d, v in rows if date.fromisoformat(d) <= target]
    if not candidates or candidates[-1][1] == 0:
        return None
    return (latest_value / candidates[-1][1] - 1) * 100


def numerical_accuracy(database: str | Path, state: dict) -> CheckResult:
    comparisons, allowed, allowed_dates = [], [], set()
    with sqlite3.connect(database) as connection:
        for result in state.get("analysis", {}).get("results", []):
            for record in result.get("records", []):
                if all(record.get(k) is not None for k in ("region_name", "metric_name", "date", "value")):
                    row = _db_value(connection, record["region_name"], record["metric_name"],
                                    record.get("geography") or result.get("geography"), record["date"])
                    ok = bool(row) and abs(float(row[0]) - float(record["value"])) <= max(0.01, abs(float(row[0])) * 1e-9)
                    comparisons.append(ok); allowed.append(float(record["value"]))
                    allowed_dates.add(record["date"][:10])
                if record.get("region_name") and "latest_value" in record:
                    allowed.append(float(record["latest_value"]))
                    if record.get("as_of_date"): allowed_dates.add(record["as_of_date"][:10])
                    for years, key in ((1, "one_year_pct"), (5, "five_year_pct")):
                        if record.get(key) is not None:
                            expected = _independent_appreciation(connection, record["region_name"], years)
                            ok = expected is not None and abs(expected - float(record[key])) <= 1e-8
                            comparisons.append(ok); allowed.append(float(record[key]))
                        comparison_date = record.get(key.replace("pct", "comparison_date"))
                        if comparison_date: allowed_dates.add(comparison_date[:10])
            for calculation in result.get("calculations", []):
                for key in ("latest_value", "1_year_pct", "5_year_pct", "left_minus_right"):
                    if calculation.get(key) is not None: allowed.append(float(calculation[key]))
                if calculation.get("latest_date"): allowed_dates.add(calculation["latest_date"][:10])
                for years in (1, 5):
                    key = f"{years}_year_pct"
                    if calculation.get(key) is not None and calculation.get("region_name"):
                        expected = _independent_change(connection, calculation["region_name"],
                            calculation.get("metric_name") or result.get("metric"),
                            calculation.get("geography") or result.get("geography"), years)
                        comparisons.append(expected is not None and
                                           abs(expected - float(calculation[key])) <= 1e-8)
                    comparison_date = calculation.get(f"{years}_year_comparison_date")
                    if comparison_date: allowed_dates.add(comparison_date[:10])
    if not comparisons and not allowed:
        return CheckResult(status="not_evaluated", detail="No structured numerical evidence was returned.")
    raw_answer = state.get("final_answer", "") or ""
    bound_claims = validate_numerical_claims(raw_answer, state.get("analysis", {}))
    date_claims = [d.replace("‑", "-").replace("–", "-") for d in
                   re.findall(r"\d{4}[-‑–]\d{2}[-‑–]\d{2}", raw_answer)]
    invalid_dates = [d for d in date_claims if d not in allowed_dates]
    answer = re.sub(r"\b(?:1|5)[-‑– ]year\b", "", raw_answer, flags=re.IGNORECASE)
    answer = re.sub(r"\d{4}[-‑–]\d{2}[-‑–]\d{2}", "", answer)
    claims = [float(x.replace(",", "")) for x in re.findall(r"(?<![\w])[-+]?\$?(\d[\d,]*(?:\.\d+)?)", answer)]
    unmatched = []
    for claim in claims:
        if claim in (1.0, 5.0): continue
        if not any(abs(claim - value) <= max(0.02, abs(value) * 0.00001) or
                   abs(abs(claim) - abs(value)) <= max(0.02, abs(value) * 0.00001) or
                   claim == round(value) or claim == round(value, 2) or claim == round(value, 3) for value in allowed):
            unmatched.append(claim)
    direction_errors = []
    for value in allowed:
        magnitude = f"{abs(value):.2f}".rstrip("0").rstrip(".")
        if value < 0 and re.search(rf"\b(?:rose|increased|grew|up)\s+{re.escape(magnitude)}\s*%", raw_answer, re.I):
            direction_errors.append(magnitude)
        if value > 0 and re.search(rf"\b(?:fell|decreased|declined|down)\s+{re.escape(magnitude)}\s*%", raw_answer, re.I):
            direction_errors.append(magnitude)
    passed = (all(comparisons) and not unmatched and not invalid_dates and not direction_errors
              and bound_claims.valid)
    return CheckResult(status="passed" if passed else "failed",
                       detail="Structured values reconciled to SQLite and answer claims matched evidence." if passed else
                              f"Reconciliation failures or unsupported claims: numbers={unmatched}, dates={invalid_dates}, direction={direction_errors}, bindings={bound_claims.unverified_claims}",
                       evidence={"structured_comparisons": len(comparisons), "answer_claims": claims,
                                 "unmatched_claims": unmatched, "date_claims": date_claims,
                                 "invalid_date_claims": invalid_dates, "direction_errors": direction_errors,
                                 "claim_bindings": bound_claims.__dict__})


def run_checks(database: str | Path, case: EvaluationCase, state: dict) -> dict[str, CheckResult]:
    return {
        "tool_selection": tool_selection(case, state),
        "location_coverage": location_coverage(case, state),
        "metric_coverage": metric_coverage(case, state),
        "behavior": behavior(case, state),
        "numerical_accuracy": numerical_accuracy(database, state),
        "workflow_completion": workflow_completion(case, state),
    }
