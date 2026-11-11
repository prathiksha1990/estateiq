# EstateIQ failure analysis

Run ID: `reliability-repair-2026-11-11`

## E07 — multi_metric_comparison

**Question:** Compare Trenton and Atlantic City metros on inventory and median sale price.

**Deterministic failures:** behavior, numerical_accuracy, workflow_completion

**Workflow error:** Market interpretation failed: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m4r7kt74e4trnbw3sghdyced` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198376, Requested 2979. Please try again in 9m45.36s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

**Judge rationale:** Not evaluated: LLM judge failed after 3 attempts: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m4r7kt74e4trnbw3sghdyced` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198369, Requested 3266. Please try again in 11m46.32s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## E13 — ambiguous_request

**Question:** How is the New Jersey housing market doing?

**Deterministic failures:** behavior, workflow_completion

**Workflow error:** Planning failed: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m4r7kt74e4trnbw3sghdyced` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199547, Requested 1291. Please try again in 6m2.016s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

**Judge rationale:** Not evaluated: LLM judge failed after 3 attempts: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m4r7kt74e4trnbw3sghdyced` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199540, Requested 866. Please try again in 2m55.392s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## E15 — unsupported_property_valuation

**Question:** Is 123 Main Street in Westfield undervalued?

**Deterministic failures:** None

**Workflow error:** None

**Judge rationale:** Not evaluated: LLM judge failed after 3 attempts: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m4r7kt74e4trnbw3sghdyced` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199529, Requested 1278. Please try again in 5m48.624s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## Recommendations

- Extend tool execution to run every requested supported metric; E07 returned inventory but omitted median sale price.
- Add deterministic preflight checks for unsupported locations and metrics so E10 and E12 terminate with explicit unavailable results instead of unresolved interrupts.
- Strengthen planner policy for ambiguous statewide requests and property-level valuation claims; E13 should request scope and E15 should explicitly refuse property valuation from town-level evidence.
- Add bounded retry or a degraded-data response for tool failures; E14 surfaced the injected error clearly but could not complete the task.
- Use `human_review.csv` for semantic cases that remain uncertain after deterministic and judge checks.
