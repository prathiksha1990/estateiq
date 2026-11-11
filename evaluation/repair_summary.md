# EstateIQ reliability repair summary

## Scope

This repair targeted multi-metric execution, metric/geography compatibility,
deterministic input guards, bounded tool recovery, and location resolution. The
Streamlit UI, source Zillow CSVs, SQLite schema, API-key handling, LangGraph
topology, and LangSmith instrumentation were preserved.

Database coverage at repair time is 495 city regions for ZHVI and four MSA
regions for the other five metrics. County, state, and ZIP requests are now
recognized as distinct geographic levels but return an explicit unavailable
result because those grains are not present in the database.

## Before and after

The baseline is `phase4-live-2026-11-11` (9/15 overall). The first clean repair
run, `phase4-repair-final-2026-11-11`, reached 13/15 before the final guard and
benchmark corrections. Later isolated runs are kept separate rather than merged
into the baseline.

| Case | Before | Observed after repair |
|---|---|---|
| E07 — multi-metric comparison | Failed because only inventory executed; median sale price was omitted. | Passed end to end in `phase4-repair-final-2026-11-11`. In the latest `reliability-repair-2026-11-11` execution, the tool stage again returned both `for_sale_inventory` and `median_sale_price` for Zillow MSA region IDs `395164` and `394348`; final interpretation was blocked by a Groq 429 quota response. |
| E10 — unsupported location | Unresolved clarification interrupt with no answer. | Passed in `reliability-repair-2026-11-11`; the deterministic guard returned an explicit unavailable-location answer without substitution. |
| E12 — unsupported metric | Unresolved clarification or evaluator behavior failure. | Passed in `reliability-repair-2026-11-11`; price-cut share is reported unavailable and no substitute metric is used. |
| E13 — broad statewide request | Incorrectly queried MSA ZHVI and claimed no NJ data was available. | Passed in `phase4-repair-final-2026-11-11`. After moving the guard ahead of the planner, it also passed in `reliability-guards-2026-11-11` by requesting city/metro and metric clarification without an LLM call. |
| E15 — property valuation | Unresolved clarification instead of a property-scope refusal. | Passed in `phase4-repair-final-2026-11-11` and `reliability-guards-2026-11-11`; the pre-LLM guard states that market-level Zillow data cannot establish whether a specific property is undervalued. |

The latest grouped live run could not produce a single five-case all-pass score
because Groq reported that its 200,000-token daily/window allowance was exhausted.
This is recorded as a provider limitation, not converted into a passing result.
Local results are retained in `evaluation/repair_run/` and
`evaluation/repair_guards/`.

## Implemented changes

### Multi-metric execution

- Every requested metric is executed independently instead of using only
  `plan.metrics[0]`.
- Successful and unavailable metrics coexist in one `AnalysisBundle`; one
  unavailable metric no longer discards successful results.
- Tool results preserve metric, unit, geography, date coverage, records, and
  resolved Zillow region IDs.
- The benchmark accepts explicitly declared equivalent tool strategies instead
  of requiring one arbitrary tool name.

### Geography and location resolution

- Planner geography recognizes city, county, ZIP, MSA, and state as distinct
  values.
- Metric compatibility is checked against the dataset metadata before querying.
- Supported locations resolve to Zillow `region_id` values, and metric queries
  use those IDs rather than name-only filtering.
- Specific metro requests remain filtered to the requested region IDs; they do
  not retrieve every MSA.
- Duplicate names trigger a clarification containing the candidate Zillow
  region IDs.
- Out-of-range date requests return the requested and available ranges.

### Deterministic guards

- Known unsupported metrics, explicit unsupported NJ locations, broad statewide
  requests, and specific-property valuation questions are handled before LLM
  analysis.
- Unsupported metric/geography combinations return their actual supported
  geography and explicitly state that no substitute was used.
- Specific-property questions terminate with a market-level data limitation.

### Retry and recovery

- SQLite operational errors identified as transient are retried at most twice
  with bounded exponential backoff.
- Permanent errors such as integrity/programming failures are not retried.
- Each failed metric returns a structured error without discarding other metric
  results.
- When every tool operation fails, the workflow terminates with a clear bounded-
  retry failure response.
- Structured Groq outputs retain bounded retries; provider exhaustion remains an
  explicit failure.

## Regression results

`PYTHONPATH=src .venv/bin/pytest -q`:

- 40 tests passed.
- 0 tests failed.
- 35 warnings remain from Streamlit's internal NumPy timedelta handling.

New or strengthened tests cover:

- multi-metric execution with one supported and one unavailable metric;
- region-ID-backed MSA filtering;
- unsupported county geography;
- duplicate location names and region-ID clarification;
- unsupported metrics and locations;
- property-level refusal;
- broad statewide clarification;
- fail-once transient recovery;
- permanent database failure without retry;
- provider structured-output retry;
- multi-turn context preservation;
- wrong numerical dates and directions.

## Remaining known issues

- The loaded database does not contain county, state, or ZIP datasets, so those
  requests cannot be answered until compatible source files are ingested.
- Price-cut share is not present in the loaded datasets.
- The grouped post-repair LLM evaluation remains partially blocked by the Groq
  token quota. E07's repaired data/tool stage is verified, but its most recent
  final interpretation did not execute successfully.
- LangSmith upload was unavailable during the local deterministic guard run due
  network/DNS restrictions; local trace IDs and evaluation artifacts were still
  recorded.
- LLM planning and interpretation remain probabilistic. Deterministic guards and
  retries reduce risk but do not eliminate provider variability.
