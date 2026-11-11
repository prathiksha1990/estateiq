# EstateIQ final failure analysis

No application case fails in the composite re-score.

## Blocked final live run

The new atomic live run was stopped after Groq returned HTTP 429 quota errors for every attempted LLM call. These provider-blocked attempts are not counted as application failures and are not included in final_results.csv.

## Manual review

Semantic interpretation, ambiguity handling, and the property-level refusal remain flagged in human_review.csv. Human scores are intentionally blank.
