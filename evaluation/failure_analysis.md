# EstateIQ failure analysis

Run ID: `phase4-repair-final-2026-11-11`

## E02 — multi_town_comparison

**Question:** Compare Westfield and Summit on latest home values and appreciation.

**Deterministic failures:** tool_selection, location_coverage, metric_coverage, behavior, workflow_completion

**Workflow error:** None

**Judge rationale:** Not evaluated

## E12 — unsupported_metric

**Question:** What is Westfield's latest price-cut share?

**Deterministic failures:** behavior

**Workflow error:** None

**Judge rationale:** The answer correctly states that the requested metric is unavailable, citing the evidence that the list of available metrics does not include a price‑cut share for Westfield. It is concise, accurate, and does not overstate any conclusions.

## Recommendations

- Extend tool execution to run every requested supported metric; E07 returned inventory but omitted median sale price.
- Add deterministic preflight checks for unsupported locations and metrics so E10 and E12 terminate with explicit unavailable results instead of unresolved interrupts.
- Strengthen planner policy for ambiguous statewide requests and property-level valuation claims; E13 should request scope and E15 should explicitly refuse property valuation from town-level evidence.
- Add bounded retry or a degraded-data response for tool failures; E14 surfaced the injected error clearly but could not complete the task.
- Use `human_review.csv` for semantic cases that remain uncertain after deterministic and judge checks.
