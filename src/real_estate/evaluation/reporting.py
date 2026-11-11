from pathlib import Path

import pandas as pd


def _rate(frame: pd.DataFrame, column: str) -> str:
    evaluated = frame[frame[column].isin(["passed", "failed"])]
    if evaluated.empty: return "Not evaluated"
    return f"{(evaluated[column] == 'passed').mean() * 100:.1f}% ({(evaluated[column] == 'passed').sum()}/{len(evaluated)})"


def _average(frame: pd.DataFrame, column: str) -> str:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return "Not evaluated" if values.empty else f"{values.mean():.2f}/5"


def generate_reports(results: pd.DataFrame, run_metadata: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total, passed = len(results), int((results["overall_pass"] == True).sum())  # noqa: E712
    interrupted = int(results["final_answer"].fillna("").eq("").sum())
    errors = int(results["workflow_error"].fillna("").ne("").sum())
    outcome_counts = results["outcome"].value_counts().to_dict() if "outcome" in results else {}
    scored = results[results.get("evaluation_status", "scored") != "excluded"] if "evaluation_status" in results else results
    latency = pd.to_numeric(results["latency_seconds"], errors="coerce").dropna()
    p95 = latency.quantile(.95) if not latency.empty else None
    categories = results.groupby("category", dropna=False)["overall_pass"].agg(["count", "sum"])
    category_lines = [f"| {idx} | {int(row['sum'])}/{int(row['count'])} | {row['sum']/row['count']*100:.1f}% |"
                      for idx, row in categories.iterrows()]
    report = f"""# EstateIQ evaluation report

## Run metadata

- Run ID: `{run_metadata['run_id']}`
- Executed: {run_metadata['execution_timestamp']}
- Model: `{run_metadata['model']}`
- Model configuration: `{run_metadata.get('model_configuration', 'Not recorded')}`
- Dataset SHA-256: `{run_metadata['dataset_sha256']}`
- Dataset latest observation: {run_metadata['dataset_latest_observation']}

## Summary

- Tests executed: **{total}**
- Passed: **{passed}**
- Failed: **{total - passed}**
- Interrupted without a final answer: **{interrupted}**
- Workflow errors: **{errors}**
- Strict task-success rate: **{outcome_counts.get('strict_success', 0) / len(scored) * 100:.1f}% ({outcome_counts.get('strict_success', 0)}/{len(scored)})**
- Partial task completion: **{outcome_counts.get('partial_task_completion', 0)}**
- Human clarification/interruption: **{outcome_counts.get('human_clarification', 0)}**
- Graceful error reporting without recovery: **{outcome_counts.get('graceful_error_reporting', 0)}**
- Successful recovery after tool failure: **{outcome_counts.get('successful_recovery', 0)}**
- Unrecovered failures: **{outcome_counts.get('unrecovered_failure', 0)}**
- Excluded/not scored: **{outcome_counts.get('not_scored', 0)}**
- Tool-selection accuracy: **{_rate(results, 'tool_selection_status')}**
- Numerical accuracy: **{_rate(results, 'numerical_accuracy_status')}**
- Numerical evaluation coverage: **{(results['numerical_accuracy_status'] != 'not_evaluated').mean() * 100:.1f}% ({(results['numerical_accuracy_status'] != 'not_evaluated').sum()}/{total})**
- Transient-error recovery rate: **{_rate(results, 'recovery_status') if 'recovery_status' in results else 'Not evaluated'}**
- Terminal-workflow rate: **{_rate(results, 'workflow_completion_status')}**
- Mean relevance: **{_average(results, 'judge_relevance_score')}**
- Mean groundedness: **{_average(results, 'judge_groundedness_score')}**
- Average latency: **{latency.mean():.2f} seconds**
- p95 latency: **{p95:.2f} seconds**

## Results by category

| Category | Passed | Pass rate |
|---|---:|---:|
{chr(10).join(category_lines)}

## Interpretation

An overall pass requires every applicable deterministic check to pass and, when an LLM judge ran, the judge to pass. “Not evaluated” checks are excluded from their metric denominator rather than treated as success. Numerical checks independently reconcile structured observations to SQLite and compare answer numbers with retrieved evidence.

## Failed cases

{_failure_examples(results)}

See `failure_analysis.md` for check-level details and recommendations. Manual review fields are available in `human_review.csv`.
"""
    (output_dir / "evaluation_report.md").write_text(report, encoding="utf-8")

    failure_rows = results[results["overall_pass"] != True]  # noqa: E712
    details = ["# EstateIQ failure analysis", "", f"Run ID: `{run_metadata['run_id']}`", ""]
    if failure_rows.empty:
        details.append("No failures were observed in this executed run.")
    else:
        for _, row in failure_rows.iterrows():
            details.extend([
                f"## {row['test_id']} — {row['category']}", "",
                f"**Question:** {row['question']}", "",
                f"**Deterministic failures:** {_clean(row['failed_checks'])}", "",
                f"**Workflow error:** {_clean(row['workflow_error'])}", "",
                f"**Judge rationale:** {'Not evaluated' if pd.isna(row['judge_rationale']) else _clean(row['judge_rationale'])}", "",
            ])
        details.extend(["## Recommendations", "",
                        "- Extend tool execution to run every requested supported metric; E07 returned inventory but omitted median sale price.",
                        "- Add deterministic preflight checks for unsupported locations and metrics so E10 and E12 terminate with explicit unavailable results instead of unresolved interrupts.",
                        "- Strengthen planner policy for ambiguous statewide requests and property-level valuation claims; E13 should request scope and E15 should explicitly refuse property valuation from town-level evidence.",
                        "- Add bounded retry or a degraded-data response for tool failures; E14 surfaced the injected error clearly but could not complete the task.",
                        "- Use `human_review.csv` for semantic cases that remain uncertain after deterministic and judge checks."])
    (output_dir / "failure_analysis.md").write_text("\n".join(details) + "\n", encoding="utf-8")


def generate_human_review(results: pd.DataFrame, path: Path) -> None:
    uncertain_categories = {"market_condition_interpretation", "ambiguous_request",
                            "unsupported_property_valuation"}
    rows = []
    for row in results.itertuples():
        uncertain = (row.category in uncertain_categories or
                     getattr(row, "evaluation_status", "scored") == "excluded" or
                     getattr(row, "judge_pass", None) is False)
        rows.append({"test_id": row.test_id, "user_question": row.question,
                     "agent_response": getattr(row, "final_answer", ""),
                     "expected_behavior": getattr(row, "expected_behavior", ""),
                     "automated_score": "pass" if getattr(row, "overall_pass", False) else "fail",
                     "human_score": "", "failure_category": getattr(row, "failed_checks", ""),
                     "reviewer_comments": "Manual semantic review requested." if uncertain else "",
                     "manual_review_required": uncertain})
    pd.DataFrame(rows).to_csv(path, index=False)


def _failure_examples(results: pd.DataFrame) -> str:
    failures = results[results["overall_pass"] != True]  # noqa: E712
    if failures.empty: return "No failed cases."
    lines = []
    for row in failures.itertuples():
        reason = _clean(row.failed_checks)
        if reason == "None": reason = _clean(row.workflow_error)
        if reason == "None": reason = "LLM judge failure"
        lines.append(f"- **{row.test_id} ({row.category})** — {reason}")
    return "\n".join(lines)


def _clean(value) -> str:
    return "None" if pd.isna(value) or value == "" else str(value)

