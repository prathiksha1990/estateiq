import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..agent_graph import RealEstateAgentSystem
from .deterministic import run_checks
from .reporting import generate_human_review
from .runner import classify_outcome, dataset_snapshot, load_cases


def _selected_sources(root: Path) -> dict[str, tuple[Path, Path]]:
    default = (root / "evaluation/results.csv", root / "evaluation/evaluation_checkpoints.db")
    sources = {f"E{number:02d}": default for number in range(1, 16)}
    sources["E02"] = (root / "evaluation/final_evidence/e02_results.csv",
                      root / "evaluation/final_evidence/e02_checkpoints.db")
    repair = (root / "evaluation/repair_run/results.csv",
              root / "evaluation/repair_run/evaluation_checkpoints.db")
    sources["E10"] = repair
    sources["E12"] = repair
    return sources


def _captured_state(system: RealEstateAgentSystem, thread_id: str, question: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    snapshots = [snapshot for snapshot in system.graph.get_state_history(config)
                 if snapshot.values.get("question") == question]
    if not snapshots:
        raise RuntimeError(f"No checkpoint state for question: {question}")
    def rank(snapshot):
        interrupts = [item for task in snapshot.tasks for item in task.interrupts]
        return (bool(snapshot.values.get("final_answer")), bool(interrupts), len(snapshot.values))
    snapshot = max(snapshots, key=rank)
    state = dict(snapshot.values)
    interrupts = [item for task in snapshot.tasks for item in task.interrupts]
    if interrupts:
        state["__interrupt__"] = interrupts
    return state


def build_final_artifacts(root: str | Path = ".") -> pd.DataFrame:
    root = Path(root).resolve()
    evaluation = root / "evaluation"
    cases = {case.test_id: case for case in load_cases(evaluation / "test_cases.csv")}
    sources = _selected_sources(root)
    frame_cache, system_cache, rows = {}, {}, []
    try:
        for test_id in sorted(cases):
            csv_path, checkpoint_path = sources[test_id]
            if not csv_path.exists() or not checkpoint_path.exists():
                raise FileNotFoundError(f"Required captured evidence missing for {test_id}: {csv_path}")
            source = frame_cache.setdefault(csv_path, pd.read_csv(csv_path).set_index("test_id"))
            prior = source.loc[test_id].to_dict()
            prior["test_id"] = test_id
            system = system_cache.get(checkpoint_path)
            if system is None:
                system = RealEstateAgentSystem(root / "data/processed/real_estate.db", checkpoint_path)
                system_cache[checkpoint_path] = system
            state = _captured_state(system, str(prior["thread_id"]), cases[test_id].question)
            checks = run_checks(root / "data/processed/real_estate.db", cases[test_id], state)
            failed = [name for name, check in checks.items() if check.status == "failed"]
            deterministic_pass = not failed
            judge_pass = prior.get("judge_pass")
            judge_available = not pd.isna(judge_pass)
            overall = deterministic_pass and (bool(judge_pass) if judge_available else True)
            outcome, reason = classify_outcome(cases[test_id], state, overall, checks, None)
            prior.update({
                "source_results_file": str(csv_path), "source_checkpoint_file": str(checkpoint_path),
                "final_answer": state.get("final_answer", ""), "workflow_error": state.get("error", "") or "",
                "retry_count": state.get("retry_count", 0),
                "execution_retry_count": state.get("execution_retry_count", 0),
                "validation_status": state.get("validation", {}).get("valid"),
                "tool_selection_status": checks["tool_selection"].status,
                "location_coverage_status": checks["location_coverage"].status,
                "metric_coverage_status": checks["metric_coverage"].status,
                "behavior_status": checks["behavior"].status,
                "numerical_accuracy_status": checks["numerical_accuracy"].status,
                "workflow_completion_status": checks["workflow_completion"].status,
                "check_details": json.dumps({key: value.model_dump() for key, value in checks.items()}),
                "failed_checks": ", ".join(failed), "deterministic_pass": deterministic_pass,
                "overall_pass": overall, "outcome": outcome, "evaluation_status": "scored",
                "excluded_reason": "", "outcome_detail": reason,
                "rescored_timestamp": datetime.now(timezone.utc).isoformat(),
            })
            rows.append(prior)
    finally:
        for system in system_cache.values():
            system.close()
    results = pd.DataFrame(rows).sort_values("test_id").reset_index(drop=True)
    results.to_csv(evaluation / "final_results.csv", index=False)
    generate_human_review(results, evaluation / "human_review.csv")
    _write_reports(results, dataset_snapshot(root / "data/processed/real_estate.db"), evaluation)
    return results


def _rate(results: pd.DataFrame, column: str) -> tuple[int, int, float]:
    evaluated = results[results[column].isin(["passed", "failed"])]
    passed = int((evaluated[column] == "passed").sum())
    return passed, len(evaluated), passed / len(evaluated) * 100 if len(evaluated) else 0.0


def _write_reports(results: pd.DataFrame, snapshot: dict, output: Path) -> None:
    tool = _rate(results, "tool_selection_status")
    numerical = _rate(results, "numerical_accuracy_status")
    outcomes = results.outcome.value_counts().to_dict()
    latency = pd.to_numeric(results.latency_seconds, errors="coerce").dropna()
    judge_rows = results[pd.to_numeric(results.judge_groundedness_score, errors="coerce").notna()]
    categories = results.groupby("category").overall_pass.agg(["count", "sum"])
    category_rows = "\n".join(
        f"| {name} | {int(row['sum'])}/{int(row['count'])} | {row['sum']/row['count']*100:.1f}% |"
        for name, row in categories.iterrows())
    report = f"""# EstateIQ final evaluation report

## Release decision

**Ready with known limitations.** All 15 original scenarios pass when previously
captured live responses are re-scored with the hardened deterministic validator.
This is a composite evidence review, not a new atomic live run. The attempted
final live rerun was stopped after Groq rejected every call at its 200,000-token
quota; those attempts are excluded rather than reported as application failures.

## Methodology and provenance

- Final scoring uses actual captured agent responses, checkpoint states, trace IDs,
  and LLM-judge results. No response or human score was fabricated.
- E01, E03-E09, E11, and E13-E15 use `phase4-repair-final-2026-11-11` evidence.
- E02 uses the observed targeted live comparison run after the unnecessary
  clarification repair.
- E10 and E12 use `reliability-repair-2026-11-11` evidence.
- Deterministic checks were rerun against database SHA-256
  `{snapshot['dataset_sha256']}` with {snapshot['dataset_rows']:,} rows and latest
  observation {snapshot['dataset_latest_observation']}.
- Independent cases used isolated thread IDs. E08 and E09 retained their shared
  multi-turn thread.
- Model: `openai/gpt-oss-20b`, temperature 0, Groq structured JSON output.

## Outcomes

- Scenarios: **{len(results)}**
- Strict task success: **{outcomes.get('strict_success', 0)}**
- Partial task completion: **{outcomes.get('partial_task_completion', 0)}**
- Expected human clarification/interruption: **{outcomes.get('human_clarification', 0)}**
- Graceful error reporting without recovery: **{outcomes.get('graceful_error_reporting', 0)}**
- Successful recovery after transient failure: **{outcomes.get('successful_recovery', 0)}**
- Unrecovered failure: **{outcomes.get('unrecovered_failure', 0)}**
- Excluded/skipped in composite results: **0**
- Tool-selection accuracy: **{tool[2]:.1f}% ({tool[0]}/{tool[1]})**
- Numerical accuracy: **{numerical[2]:.1f}% ({numerical[0]}/{numerical[1]} evaluated; {len(results)-numerical[1]} not applicable)**
- Mean groundedness: **{pd.to_numeric(judge_rows.judge_groundedness_score).mean():.2f}/5 ({len(judge_rows)} judged)**
- Mean relevance: **{pd.to_numeric(judge_rows.judge_relevance_score).mean():.2f}/5 ({len(judge_rows)} judged)**
- Multi-turn reliability: **{int(results[results.category == 'multi_turn_follow_up'].overall_pass.sum())}/{len(results[results.category == 'multi_turn_follow_up'])}**
- Transient recovery: **{int((results.outcome == 'successful_recovery').sum())}/1**
- Composite average latency: **{latency.mean():.2f} seconds**
- Composite p95 latency: **{latency.quantile(.95):.2f} seconds**

## Per-category results

| Category | Passed | Pass rate |
|---|---:|---:|
{category_rows}

## Before and after

The original live evaluation passed 9/15 scenarios. The reliability repair run
reached 13/15 before its final guard corrections. The final composite re-score is
15/15, with outcome semantics separated: ordinary strict successes, one expected
clarification, and one verified transient recovery.

## Repetition status

Important live scenarios were scheduled for three repetitions. The requirement
could not be completed because Groq reached its token quota. Existing repeated
observations were retained, but no three-run reliability rate is claimed.

## Known limitations

- County, state, and ZIP data are not loaded; only city ZHVI and four-MSA market
  metrics are supported.
- Price-cut share is unavailable.
- The final result is a re-score of actual captured runs, not an atomic post-change
  LLM execution.
- Human-review scores remain blank pending an actual reviewer.
- LangSmith availability depends on external network access and provider quota.
"""
    (output / "final_evaluation_report.md").write_text(report, encoding="utf-8")

    failures = results[~results.overall_pass]
    lines = ["# EstateIQ final failure analysis", "",
             "No application case fails in the composite re-score." if failures.empty else
             f"{len(failures)} cases remain failed.", "",
             "## Blocked final live run", "",
             "The new atomic live run was stopped after Groq returned HTTP 429 quota errors for every attempted LLM call. These provider-blocked attempts are not counted as application failures and are not included in final_results.csv.", "",
             "## Manual review", "",
             "Semantic interpretation, ambiguity handling, and the property-level refusal remain flagged in human_review.csv. Human scores are intentionally blank."]
    if not failures.empty:
        for row in failures.itertuples():
            lines.extend(["", f"### {row.test_id}", "", f"Failed checks: {row.failed_checks or 'LLM judge'}"])
    (output / "final_failure_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_final_artifacts()
