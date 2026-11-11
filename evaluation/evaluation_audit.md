# EstateIQ evaluation audit

This file records the controlling findings from the comprehensive audit that
preceded the reliability and final-validation repairs. The requested file did
not previously exist; the findings were recovered from `evaluation_report.md`,
`failure_analysis.md`, `results.csv`, checkpoint state, SQLite, and LangSmith
trace inspection.

## Audited baseline

- Run: `phase4-live-2026-11-11`
- Cases: 15
- Passed: 9
- Failed: 6
- Reported tool selection: 12/15
- Numerical checks: 10/10 evaluated, with five not evaluated
- Reported task completion: 12/15, which mixed successful answers with partial
  and error-only terminal responses
- Mean relevance and groundedness: 4.67/5 over 12 judged cases
- Average/p95 latency: 18.09/39.09 seconds

## Material findings

1. The executor used only `plan.metrics[0]`, omitting later requested metrics.
2. Specific MSA questions sometimes lost their location and retrieved all MSAs.
3. Unsupported locations, metrics, and property-level requests became unresolved
   clarification interrupts.
4. A broad statewide request queried MSA ZHVI, found no records, and incorrectly
   concluded that no New Jersey market data was available.
5. The injected tool failure was surfaced but not recovered; the original 100%
   recovery statistic measured error reporting rather than recovery.
6. Tool scoring credited a planned tool as executed in the failure-injection case.
7. Numerical checking reconciled values but did not fully bind every answer claim
   to its metric, location, geography, date, unit, and direction.
8. The LLM judge approved incomplete answers when the supplied evidence itself
   omitted a requested metric.
9. The result set combined targeted reruns under one run ID, so it was not an
   atomic execution.
10. Human-review fields were empty.

## Data findings

The SQLite database passed integrity and duplicate-grain checks. It contained
161,883 rows, 495 city ZHVI regions, four MSA regions for the other metrics, and
16,270 preserved null ZHVI observations. The audit found no demonstrated
fabricated numerical value in the ten numerically evaluated baseline cases.

## Repair disposition

The execution, geography, guard, retry, outcome-accounting, and deterministic
claim-binding issues are addressed in the current source and regression suite.
See `repair_summary.md` and `final_evaluation_report.md` for observed post-repair
evidence and remaining limitations.
