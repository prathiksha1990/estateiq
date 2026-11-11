# EstateIQ evaluation summary

## Result

EstateIQ is **ready with known limitations**. The final evidence-backed composite review scores all 15 original scenarios as passing, while explicitly separating one expected clarification and one recovered transient failure from ordinary strict success.

## Methodology

- Fifteen versioned scenarios from `evaluation/test_cases.csv`.
- Actual captured Groq responses, LangGraph checkpoint state, trace IDs, and database evidence.
- Deterministic SQLite reconciliation and claim binding.
- Structured LLM judge where available.
- Isolated threads for independent cases; one shared thread for E08–E09.
- Empty human scores pending real review.

The final evidence is composite rather than one new atomic run. A final live attempt was stopped after Groq rejected all model calls at its token quota. Those attempts were excluded, not counted as application failures.

## Final metrics

| Metric | Observed result | Denominator / qualification |
|---|---:|---|
| Original scenarios | 15 | All represented in `final_results.csv` |
| Strict task success | 13 | 13/15; clarification and recovery reported separately |
| Partial completion | 0 | 0/15 |
| Expected clarification | 1 | E13 |
| Successful recovery | 1 | E14 fail-once transient tool error |
| Graceful error without recovery | 0 | 0/15 |
| Unrecovered failures | 0 | 0/15 composite evidence |
| Tool-selection accuracy | 100% | 15/15 |
| Numerical accuracy | 100% | 11/11 applicable; four not evaluated because no numerical claim applied |
| Mean groundedness | 5.00/5 | 14 LLM-judged cases |
| Mean relevance | 5.00/5 | 14 LLM-judged cases |
| Multi-turn reliability | 100% | 2/2 cases |
| Recovery success | 100% | 1/1 injected transient failure; not graceful-error reporting |
| Composite average latency | 17.86 seconds | Values came from selected source executions |
| Composite p95 latency | 41.78 seconds | Not an atomic-run latency distribution |
| Automated tests | 48 passed | 35 Streamlit/NumPy deprecation warnings |

No human-review score has been measured. Three semantic cases are flagged for manual review. No three-repeat live reliability rate was measured because of the Groq quota.

## Per-category status

Every represented category passed in the composite evidence: single-town analysis, multi-town comparison, historical appreciation, inventory, sales, market-condition interpretation, multi-metric comparison, multi-turn follow-up, missing history, unsupported location, unsupported metric, ambiguity, transient failure, and property-scope refusal.

## Before and after

| Stage | Result | Important observation |
|---|---:|---|
| Original live evaluation | 9/15 | Multi-metric, unsupported-input, ambiguity, recovery, and property-scope failures |
| First clean repair run | 13/15 | Major reliability repairs worked; two final behavior/benchmark issues remained |
| Final composite re-score | 15/15 | Hardened deterministic validation and corrected outcome accounting |

## Significant repaired failures

- E07 now executes inventory and median sale price independently instead of dropping the second metric.
- E10 returns a deterministic unsupported-location response.
- E12 reports price-cut share unavailable without substituting another metric.
- E13 requests scope rather than claiming that New Jersey data is unavailable.
- E14 retries a transient failure and actually recovers.
- E15 refuses individual-property valuation from town-level data.

## Remaining limitations

- The final result is composite evidence, not a new atomic post-change run.
- Three planned repetitions of important LLM scenarios were blocked by quota.
- County, state, ZIP, and price-cut-share data are not loaded.
- Human review is pending.
- LangSmith trace upload depends on network availability.

Detailed evidence: `evaluation/final_evaluation_report.md`, `evaluation/final_results.csv`, `evaluation/final_failure_analysis.md`, `evaluation/evaluation_audit.md`, and `evaluation/repair_summary.md`.
