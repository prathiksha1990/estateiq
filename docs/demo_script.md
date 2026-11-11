# EstateIQ five-minute demo script

## 0:00–0:30 — Introduction

“EstateIQ is a New Jersey real-estate market intelligence application. Comparing towns normally requires reconciling home values, prices, inventory, sales activity, and market-speed files with different coverage. EstateIQ creates one validated local data layer and lets users explore it through dashboards or a constrained multi-agent research workflow.”

Show the EstateIQ sidebar and four pages. Do not show `.env` or terminal output containing credentials.

## 0:30–1:00 — Data pipeline and architecture

Open **Agent activity & data sources**.

“The application uses independently downloaded Zillow Research CSVs. The ingestion pipeline filters New Jersey, normalizes monthly columns, preserves missing values, and writes an indexed SQLite database. ZHVI is city-level and represents typical home value; median sale price and the other current market metrics are MSA-level.”

Briefly point to dataset freshness and the architecture panel. Explain that tools are fixed and read-only; the LLM cannot generate SQL or calculate values.

## 1:00–2:15 — Real market comparison

Open **AI market analyst** and submit:

> Compare Westfield and Summit on latest home values and appreciation.

“This is a verified supported question. Both locations have city-level ZHVI coverage. The workflow retrieves actual observations and Python-calculated one- and five-year appreciation. It should label the metric as ZHVI, include dates and percentages, and avoid treating it as median sale price.”

Show the answer and supporting data. If Groq is quota-blocked during recording, use the already captured response in `evaluation/final_results.csv` and state that it is recorded evaluation evidence; do not pretend a failed live call succeeded.

Optionally open **Compare markets** and select Westfield and Summit to show the source-backed trend chart.

## 2:15–3:15 — Agent orchestration

Expand execution details or open **Agent activity & data sources**.

“The Research Planner produces a structured plan. The Data Analysis stage resolves Zillow region IDs and calls approved database functions. The Market Intelligence Agent explains only returned evidence. A deterministic claim validator binds every number to its metric, location, geography, date, unit, value, and direction. The Answer Validation Agent can route an invalid draft back for at most two corrections.”

Point to the actual agents, tools invoked, validation status, retry count, source database, and trace metadata. Do not describe private chain-of-thought.

## 3:15–4:00 — Validation and error handling

Use one of these verified questions:

> What is Westfield's latest price-cut share?

Expected result: price-cut share is not available; EstateIQ must not substitute another metric.

Then mention the property-scope guard with:

> Is 123 Main Street in Westfield undervalued?

Expected result: town-level Zillow data cannot determine whether an individual property is undervalued. This guard executes before LLM analysis.

If time permits, mention that the evaluation also injects a transient tool failure; the first call fails, a bounded retry succeeds, and recovery is recorded separately from graceful error reporting.

## 4:00–4:40 — Evaluation and iteration

Open `evaluation/final_evaluation_report.md` or show its key figures in the repository.

“The original evaluation passed 9 of 15 cases. Failures exposed dropped secondary metrics, weak unsupported-input handling, false statewide conclusions, and error reporting mislabeled as recovery. After repair, the composite evidence set contains 13 strict successes, one expected clarification, and one successful transient recovery. Tool selection is 15 of 15, numerical validation is 11 of 11 applicable cases, and 48 regression tests pass.”

Clearly add: “This final 15-case result re-scores actual captured live responses. A fresh atomic run and three-repeat reliability measurement were blocked by the Groq token quota.”

## 4:40–5:00 — Close

“EstateIQ demonstrates an end-to-end data and agent system: ingestion, validation, deterministic calculations, constrained tools, stateful orchestration, transparent UI, and evaluation-driven repair. The next steps are broader geographic data, price-cut coverage, independent human review, and repeated live evaluation after quota reset.”

End on Market Overview or the README architecture diagram.
