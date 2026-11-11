# EstateIQ evaluation report

## Run metadata

- Run ID: `phase4-repair-final-2026-11-11`
- Executed: 2026-11-11T17:43:09.158258+00:00
- Model: `openai/gpt-oss-20b`
- Model configuration: `{"max_provider_retries": 2, "model": "openai/gpt-oss-20b", "provider": "Groq", "structured_output": "json_schema", "temperature": 0}`
- Dataset SHA-256: `afb5e725270bce0fee239fa7d728a229d511c730a61d83aa9946c83713b502e2`
- Dataset latest observation: 2026-09-30

## Summary

- Tests executed: **15**
- Passed: **13**
- Failed: **2**
- Interrupted without a final answer: **2**
- Workflow errors: **0**
- Strict task-success rate: **86.7% (13/15)**
- Tool-selection accuracy: **93.3% (14/15)**
- Numerical accuracy: **100.0% (10/10)**
- Numerical evaluation coverage: **66.7% (10/15)**
- Transient-error recovery rate: **100.0% (1/1)**
- Terminal-workflow rate: **93.3% (14/15)**
- Mean relevance: **5.00/5**
- Mean groundedness: **5.00/5**
- Average latency: **19.53 seconds**
- p95 latency: **41.78 seconds**

## Results by category

| Category | Passed | Pass rate |
|---|---:|---:|
| ambiguous_request | 1/1 | 100.0% |
| historical_appreciation | 1/1 | 100.0% |
| inventory_analysis | 1/1 | 100.0% |
| market_condition_interpretation | 1/1 | 100.0% |
| missing_and_insufficient_data | 1/1 | 100.0% |
| multi_metric_comparison | 1/1 | 100.0% |
| multi_town_comparison | 0/1 | 0.0% |
| multi_turn_follow_up | 2/2 | 100.0% |
| sales_analysis | 1/1 | 100.0% |
| simulated_tool_failure | 1/1 | 100.0% |
| single_town_analysis | 1/1 | 100.0% |
| unsupported_location | 1/1 | 100.0% |
| unsupported_metric | 0/1 | 0.0% |
| unsupported_property_valuation | 1/1 | 100.0% |

## Interpretation

An overall pass requires every applicable deterministic check to pass and, when an LLM judge ran, the judge to pass. “Not evaluated” checks are excluded from their metric denominator rather than treated as success. Numerical checks independently reconcile structured observations to SQLite and compare answer numbers with retrieved evidence.

## Failed cases

- **E02 (multi_town_comparison)** — tool_selection, location_coverage, metric_coverage, behavior, workflow_completion
- **E12 (unsupported_metric)** — behavior

See `failure_analysis.md` for check-level details and recommendations. Manual review fields are available in `human_review.csv`.
