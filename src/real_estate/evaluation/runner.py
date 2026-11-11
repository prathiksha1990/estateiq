import argparse
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from langchain_groq import ChatGroq

from ..agent_graph import RealEstateAgentSystem, create_groq_model
from .deterministic import run_checks
from .judge import LLMJudge
from .models import EvaluationCase
from .reporting import generate_human_review, generate_reports


def classify_outcome(case: EvaluationCase, state: dict, overall: bool,
                     checks: dict, judge_error: str | None) -> tuple[str, str]:
    if judge_error:
        return "not_scored", f"LLM judge unavailable: {judge_error}"
    interrupted = bool(state.get("__interrupt__"))
    if interrupted and case.expected_behavior == "clarification":
        return "human_clarification", "Expected clarification interrupt."
    if case.failure_injection and state.get("execution_retry_count", 0) > 0 and overall:
        return "successful_recovery", "Transient tool failure recovered after bounded retry."
    if overall:
        return "strict_success", "All applicable deterministic and judge checks passed."
    results = state.get("analysis", {}).get("results", [])
    has_answer = bool(state.get("final_answer"))
    if has_answer and (state.get("error") or (results and all(r.get("status") == "error" for r in results))):
        return "graceful_error_reporting", "Failure was surfaced clearly but the task did not recover."
    if has_answer and any(r.get("status") == "ok" for r in results):
        return "partial_task_completion", "Some evidence was returned, but one or more required checks failed."
    return "unrecovered_failure", "No valid completed answer or expected clarification was produced."


def load_cases(path: str | Path) -> list[EvaluationCase]:
    frame = pd.read_csv(path, keep_default_na=False)
    cases = []
    for row in frame.to_dict(orient="records"):
        for column in ("expected_tools", "expected_metrics", "expected_locations"):
            row[column] = json.loads(row[column])
        row["conversation_group"] = row["conversation_group"] or None
        row["failure_injection"] = row["failure_injection"] or None
        cases.append(EvaluationCase.model_validate(row))
    return cases


def dataset_snapshot(database: str | Path) -> dict:
    path = Path(database)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path) as connection:
        latest = connection.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        rows = connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    return {"dataset_sha256": digest, "dataset_latest_observation": latest, "dataset_rows": rows}


@contextmanager
def inject_failure(system: RealEstateAgentSystem, method_name: str | None):
    if not method_name:
        yield; return
    if not hasattr(system.toolkit, method_name):
        raise ValueError(f"Unknown failure injection target: {method_name}")
    original = getattr(system.toolkit, method_name)
    failed = False
    def fail(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise sqlite3.OperationalError(f"Injected transient {method_name} failure")
        return original(*args, **kwargs)
    setattr(system.toolkit, method_name, fail)
    try: yield
    finally: setattr(system.toolkit, method_name, original)


class EvaluationRunner:
    def __init__(self, database: str | Path, cases_path: str | Path,
                 output_dir: str | Path = "evaluation", run_id: str | None = None,
                 use_llm_judge: bool = True, max_attempts: int = 3,
                 test_ids: set[str] | None = None, merge_results: bool = False):
        self.database, self.cases_path = Path(database), Path(cases_path)
        self.output_dir = Path(output_dir)
        self.run_id = run_id or datetime.now(timezone.utc).strftime("eval-%Y%m%dT%H%M%SZ")
        self.max_attempts = max_attempts
        self.test_ids, self.merge_results = test_ids, merge_results
        self.system = RealEstateAgentSystem(self.database, self.output_dir / "evaluation_checkpoints.db")
        self.judge = LLMJudge(create_groq_model(), max_attempts) if use_llm_judge else None

    def close(self):
        self.system.close()

    def _invoke(self, case: EvaluationCase, thread_id: str, trace_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}, "run_id": uuid.UUID(trace_id),
                  "run_name": f"evaluation:{case.test_id}",
                  "metadata": {"evaluation_run_id": self.run_id, "test_id": case.test_id,
                               "category": case.category}}
        last_error = None
        for attempt in range(self.max_attempts):
            try:
                with inject_failure(self.system, case.failure_injection):
                    return self.system.graph.invoke({"question": case.question}, config)
            except Exception as exc:
                last_error = exc
                if attempt + 1 == self.max_attempts: break
                time.sleep(2 ** attempt)
        return {"question": case.question, "error": str(last_error),
                "final_answer": f"Evaluation invocation failed: {last_error}", "retry_count": self.max_attempts - 1}

    def run(self) -> tuple[pd.DataFrame, dict]:
        cases = load_cases(self.cases_path)
        if self.test_ids:
            cases = [case for case in cases if case.test_id in self.test_ids]
        existing = None
        results_path = self.output_dir / "results.csv"
        if self.merge_results and results_path.exists():
            existing = pd.read_csv(results_path)
        group_threads, rows = {}, []
        snapshot = dataset_snapshot(self.database)
        model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        model_configuration = json.dumps({"provider": "Groq", "model": model_name, "temperature": 0,
                                          "structured_output": "json_schema", "max_provider_retries": 2}, sort_keys=True)
        metadata = {"run_id": self.run_id, "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                    "model": model_name, "model_configuration": model_configuration, **snapshot}
        for case in cases:
            if rows:
                time.sleep(1.0)
            print(f"[{case.test_id}] {case.category}: running", flush=True)
            thread_id = group_threads.setdefault(case.conversation_group, str(uuid.uuid4())) if case.conversation_group else str(uuid.uuid4())
            trace_id = str(uuid.uuid4())
            started = time.perf_counter()
            state = self._invoke(case, thread_id, trace_id)
            latency = time.perf_counter() - started
            checks = run_checks(self.database, case, state)
            compact = self.system._compact_analysis(state.get("analysis", {}))
            judge, judge_error = None, None
            if self.judge and not state.get("__interrupt__"):
                try: judge = self.judge.evaluate(case, compact, state.get("final_answer", ""))
                except Exception as exc: judge_error = str(exc)
            failed_checks = [name for name, check in checks.items() if check.status == "failed"]
            deterministic_pass = not failed_checks
            overall = deterministic_pass and (judge.passed if judge else True) and not judge_error
            outcome, excluded_reason = classify_outcome(case, state, overall, checks, judge_error)
            row = {
                "run_id": self.run_id, "test_id": case.test_id, "category": case.category,
                "question": case.question, "expected_behavior": case.expected_behavior,
                "conversation_group": case.conversation_group, "thread_id": thread_id, "trace_id": trace_id,
                "model": metadata["model"], "dataset_sha256": snapshot["dataset_sha256"],
                "model_configuration": model_configuration,
                "execution_timestamp": datetime.now(timezone.utc).isoformat(), "latency_seconds": round(latency, 4),
                "retry_count": state.get("retry_count", 0), "validation_status": state.get("validation", {}).get("valid"),
                "execution_retry_count": state.get("execution_retry_count", 0),
                "final_answer": state.get("final_answer", ""), "workflow_error": state.get("error", ""),
                "failure_injection": case.failure_injection, "tools_invoked": json.dumps([r.get("tool") for r in state.get("analysis", {}).get("results", [])]),
                "metrics_returned": json.dumps([r.get("metric") for r in state.get("analysis", {}).get("results", [])]),
                "tool_selection_status": checks["tool_selection"].status,
                "location_coverage_status": checks["location_coverage"].status,
                "metric_coverage_status": checks["metric_coverage"].status,
                "behavior_status": checks["behavior"].status,
                "numerical_accuracy_status": checks["numerical_accuracy"].status,
                "workflow_completion_status": checks["workflow_completion"].status,
                "recovery_status": ("passed" if state.get("execution_retry_count", 0) > 0 and not state.get("error")
                                    else "failed") if case.failure_injection else "not_evaluated",
                "check_details": json.dumps({k: v.model_dump() for k, v in checks.items()}),
                "failed_checks": ", ".join(failed_checks), "deterministic_pass": deterministic_pass,
                "judge_relevance_score": judge.relevance_score if judge else None,
                "judge_groundedness_score": judge.groundedness_score if judge else None,
                "judge_clarity_score": judge.clarity_score if judge else None,
                "judge_overstatement_score": judge.overstatement_score if judge else None,
                "judge_pass": judge.passed if judge else None,
                "judge_rationale": judge.rationale if judge else (f"Not evaluated: {judge_error}" if judge_error else "Not evaluated"),
                "overall_pass": overall, "outcome": outcome,
                "evaluation_status": "excluded" if outcome == "not_scored" else "scored",
                "excluded_reason": excluded_reason if outcome == "not_scored" else "",
            }
            rows.append(row)
            partial = pd.DataFrame(rows)
            if existing is not None:
                partial = pd.concat([existing[~existing["test_id"].isin(partial["test_id"])], partial], ignore_index=True)
                partial = partial.sort_values("test_id")
            partial.to_csv(results_path, index=False)
            print(f"[{case.test_id}] {'PASS' if overall else 'FAIL'} in {latency:.2f}s"
                  f" (failed checks: {', '.join(failed_checks) or 'none'})", flush=True)
        results = pd.DataFrame(rows)
        if existing is not None:
            results = pd.concat([existing[~existing["test_id"].isin(results["test_id"])], results], ignore_index=True)
            results = results.sort_values("test_id").reset_index(drop=True)
        generate_reports(results, metadata, self.output_dir)
        generate_human_review(results, self.output_dir / "human_review.csv")
        (self.output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return results, metadata


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the full EstateIQ LangGraph workflow")
    parser.add_argument("--database", default="data/processed/real_estate.db")
    parser.add_argument("--cases", default="evaluation/test_cases.csv")
    parser.add_argument("--output-dir", default="evaluation")
    parser.add_argument("--run-id")
    parser.add_argument("--skip-llm-judge", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--test-ids", help="Comma-separated case IDs to execute")
    parser.add_argument("--merge-results", action="store_true", help="Merge selected cases into an existing results.csv")
    args = parser.parse_args(argv)
    test_ids = {x.strip() for x in args.test_ids.split(",")} if args.test_ids else None
    runner = EvaluationRunner(args.database, args.cases, args.output_dir, args.run_id,
                              not args.skip_llm_judge, args.max_attempts, test_ids, args.merge_results)
    try:
        results, _ = runner.run()
        print(f"Executed {len(results)} tests: {int(results.overall_pass.sum())} passed, {int((~results.overall_pass).sum())} failed")
    finally: runner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
