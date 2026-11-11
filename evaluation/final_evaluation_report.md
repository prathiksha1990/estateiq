# EstateIQ final evaluation report

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
  `afb5e725270bce0fee239fa7d728a229d511c730a61d83aa9946c83713b502e2` with 161,883 rows and latest
  observation 2026-09-30.
- Independent cases used isolated thread IDs. E08 and E09 retained their shared
  multi-turn thread.
- Model: `openai/gpt-oss-20b`, temperature 0, Groq structured JSON output.

## Outcomes

- Scenarios: **15**
- Strict task success: **13**
- Partial task completion: **0**
- Expected human clarification/interruption: **1**
- Graceful error reporting without recovery: **0**
- Successful recovery after transient failure: **1**
- Unrecovered failure: **0**
- Excluded/skipped in composite results: **0**
- Tool-selection accuracy: **100.0% (15/15)**
- Numerical accuracy: **100.0% (11/11 evaluated; 4 not applicable)**
- Mean groundedness: **5.00/5 (14 judged)**
- Mean relevance: **5.00/5 (14 judged)**
- Multi-turn reliability: **2/2**
- Transient recovery: **1/1**
- Composite average latency: **17.86 seconds**
- Composite p95 latency: **41.78 seconds**

## Per-category results

| Category | Passed | Pass rate |
|---|---:|---:|
| ambiguous_request | 1/1 | 100.0% |
| historical_appreciation | 1/1 | 100.0% |
| inventory_analysis | 1/1 | 100.0% |
| market_condition_interpretation | 1/1 | 100.0% |
| missing_and_insufficient_data | 1/1 | 100.0% |
| multi_metric_comparison | 1/1 | 100.0% |
| multi_town_comparison | 1/1 | 100.0% |
| multi_turn_follow_up | 2/2 | 100.0% |
| sales_analysis | 1/1 | 100.0% |
| simulated_tool_failure | 1/1 | 100.0% |
| single_town_analysis | 1/1 | 100.0% |
| unsupported_location | 1/1 | 100.0% |
| unsupported_metric | 1/1 | 100.0% |
| unsupported_property_valuation | 1/1 | 100.0% |

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
