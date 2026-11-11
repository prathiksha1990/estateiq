# EstateIQ evaluation report

## Run metadata

- Run ID: `reliability-repair-2026-11-11`
- Executed: 2026-11-11T18:00:48.156471+00:00
- Model: `openai/gpt-oss-20b`
- Model configuration: `{"max_provider_retries": 2, "model": "openai/gpt-oss-20b", "provider": "Groq", "structured_output": "json_schema", "temperature": 0}`
- Dataset SHA-256: `afb5e725270bce0fee239fa7d728a229d511c730a61d83aa9946c83713b502e2`
- Dataset latest observation: 2026-09-30

## Summary

- Tests executed: **5**
- Passed: **2**
- Failed: **3**
- Interrupted without a final answer: **0**
- Workflow errors: **2**
- Strict task-success rate: **40.0% (2/5)**
- Tool-selection accuracy: **100.0% (5/5)**
- Numerical accuracy: **0.0% (0/1)**
- Numerical evaluation coverage: **20.0% (1/5)**
- Transient-error recovery rate: **Not evaluated**
- Terminal-workflow rate: **60.0% (3/5)**
- Mean relevance: **5.00/5**
- Mean groundedness: **5.00/5**
- Average latency: **1.08 seconds**
- p95 latency: **2.55 seconds**

## Results by category

| Category | Passed | Pass rate |
|---|---:|---:|
| ambiguous_request | 0/1 | 0.0% |
| multi_metric_comparison | 0/1 | 0.0% |
| unsupported_location | 1/1 | 100.0% |
| unsupported_metric | 1/1 | 100.0% |
| unsupported_property_valuation | 0/1 | 0.0% |

## Interpretation

An overall pass requires every applicable deterministic check to pass and, when an LLM judge ran, the judge to pass. “Not evaluated” checks are excluded from their metric denominator rather than treated as success. Numerical checks independently reconcile structured observations to SQLite and compare answer numbers with retrieved evidence.

## Failed cases

- **E07 (multi_metric_comparison)** — behavior, numerical_accuracy, workflow_completion
- **E13 (ambiguous_request)** — behavior, workflow_completion
- **E15 (unsupported_property_valuation)** — LLM judge failure

See `failure_analysis.md` for check-level details and recommendations. Manual review fields are available in `human_review.csv`.
