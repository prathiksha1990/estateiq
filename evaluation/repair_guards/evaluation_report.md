# EstateIQ evaluation report

## Run metadata

- Run ID: `reliability-guards-2026-11-11`
- Executed: 2026-11-11T18:02:29.717680+00:00
- Model: `openai/gpt-oss-20b`
- Model configuration: `{"max_provider_retries": 2, "model": "openai/gpt-oss-20b", "provider": "Groq", "structured_output": "json_schema", "temperature": 0}`
- Dataset SHA-256: `afb5e725270bce0fee239fa7d728a229d511c730a61d83aa9946c83713b502e2`
- Dataset latest observation: 2026-09-30

## Summary

- Tests executed: **4**
- Passed: **4**
- Failed: **0**
- Interrupted without a final answer: **1**
- Workflow errors: **0**
- Strict task-success rate: **100.0% (4/4)**
- Tool-selection accuracy: **100.0% (4/4)**
- Numerical accuracy: **Not evaluated**
- Numerical evaluation coverage: **0.0% (0/4)**
- Transient-error recovery rate: **Not evaluated**
- Terminal-workflow rate: **100.0% (4/4)**
- Mean relevance: **Not evaluated**
- Mean groundedness: **Not evaluated**
- Average latency: **0.25 seconds**
- p95 latency: **0.25 seconds**

## Results by category

| Category | Passed | Pass rate |
|---|---:|---:|
| ambiguous_request | 1/1 | 100.0% |
| unsupported_location | 1/1 | 100.0% |
| unsupported_metric | 1/1 | 100.0% |
| unsupported_property_valuation | 1/1 | 100.0% |

## Interpretation

An overall pass requires every applicable deterministic check to pass and, when an LLM judge ran, the judge to pass. “Not evaluated” checks are excluded from their metric denominator rather than treated as success. Numerical checks independently reconcile structured observations to SQLite and compare answer numbers with retrieved evidence.

## Failed cases

No failed cases.

See `failure_analysis.md` for check-level details and recommendations. Manual review fields are available in `human_review.csv`.
