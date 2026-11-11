import streamlit as st

from real_estate.ui_components import execution_details
from real_estate.ui_runtime import cached_transparency

st.title("Agent activity & data sources")
st.caption("Inspect the system that produced the analysis and the freshness of every loaded dataset.")

st.subheader("LangGraph agent team", icon=":material/account_tree:")
agents = [
    ("Research planner", ":material/assignment:", "Interprets the question and produces a typed research plan."),
    ("Data analysis agent", ":material/database:", "Runs approved read-only tools and deterministic calculations."),
    ("Market intelligence agent", ":material/insights:", "Separates data observations, interpretations, and limitations."),
    ("Answer validation agent", ":material/verified:", "Checks numeric claims, dates, units, geography, and answer coverage."),
]
with st.grid(4, min_column_width=220, gap="medium"):
    for name, icon, description in agents:
        with st.container(border=True, height="stretch"):
            st.subheader(name, icon=icon)
            st.caption(description)

st.subheader("Latest execution", icon=":material/history:")
execution_details(st.session_state.last_agent_state, expanded=True)

st.subheader("Dataset freshness", icon=":material/update:")
metadata = cached_transparency()
st.dataframe(
    metadata,
    hide_index=True,
    width="stretch",
    alt="Zillow Research dataset coverage and latest observation dates",
    column_config={
        "Dataset metric": st.column_config.TextColumn("Metric"),
        "Coverage": st.column_config.TextColumn("Geography"),
        "First observation": st.column_config.DateColumn("First observation", format="MMM YYYY"),
        "Latest observation": st.column_config.DateColumn("Latest observation", format="MMM YYYY"),
        "Populated observations": st.column_config.NumberColumn("Observations", format="localized"),
    },
)

with st.container(border=True):
    st.subheader("How EstateIQ works", icon=":material/schema:")
    st.markdown("""
    A natural-language question enters a typed LangGraph workflow. The planner selects only approved tools, the analysis agent reads the local SQLite database, the market-intelligence agent drafts an evidence-based response, and the validation agent either approves it or returns it for correction. Conversation checkpoints preserve follow-up context by thread ID.

    **Data source:** Zillow Research CSV datasets supplied locally by the project owner. EstateIQ is not affiliated with or endorsed by Zillow. ZHVI is a modeled typical home-value index—not an appraisal or observed sale price. Median sale price is a separate transaction metric.
    """)
    st.warning("City ZHVI and MSA market activity describe different geographic levels. Missing observations remain missing and are never replaced with zero.", icon=":material/info:")
