import streamlit as st

from real_estate.ui_components import comparison_display, format_value, insight_panel, line_chart, metric_card
from real_estate.ui_runtime import (cached_comparison, cached_comparison_trends,
                                    cached_locations, get_agent_system)

st.title("Compare markets")
st.caption("Compare city home values and MSA activity without blending incompatible geographic levels.")

town_choices = cached_locations("city")
msa_choices = cached_locations("msa")
st.session_state.comparison_towns = [x for x in st.session_state.comparison_towns if x in town_choices][:3]
st.session_state.comparison_msas = [x for x in st.session_state.comparison_msas if x in msa_choices][:3]

with st.container(border=True):
    controls = st.columns(2, gap="large")
    towns = controls[0].multiselect("Cities — ZHVI and appreciation", town_choices, max_selections=3,
                                   key="comparison_towns", persist_state="session")
    msas = controls[1].multiselect("Market areas — inventory and activity", msa_choices, max_selections=3,
                                  key="comparison_msas", persist_state="session")

if not towns and not msas:
    st.info("Select at least one city or market area to begin.", icon=":material/location_city:")
    st.stop()

if towns:
    city_table = cached_comparison(tuple(towns), "city")
    st.subheader("City home value comparison", icon=":material/location_city:")
    with st.container(horizontal=True):
        for _, row in city_table.iterrows():
            metric_card(row["Location"],
                        format_value(row["Typical home value"], "Typical home value"),
                        row["1-year appreciation"], "1-year appreciation", row["ZHVI date"])
    with st.container(border=True):
        line_chart(cached_comparison_trends(tuple(towns), "zhvi", "city", 5),
                   "Five-year home value trend", "ZHVI (USD)", color="region_name",
                   alt="Five-year ZHVI comparison for selected New Jersey cities")
    comparison_display(city_table)

if msas:
    msa_table = cached_comparison(tuple(msas), "msa")
    st.subheader("Market activity comparison", icon=":material/query_stats:")
    comparison_display(msa_table)
    activity_cols = st.columns(2, gap="large")
    with activity_cols[0]:
        with st.container(border=True):
            line_chart(cached_comparison_trends(tuple(msas), "for_sale_inventory", "msa", 5),
                       "For-sale inventory", "Homes", color="region_name",
                       alt="For-sale inventory comparison for selected New Jersey MSAs")
    with activity_cols[1]:
        with st.container(border=True):
            line_chart(cached_comparison_trends(tuple(msas), "median_days_to_pending", "msa", 5),
                       "Median days to pending", "Days", color="region_name",
                       alt="Days-to-pending comparison for selected New Jersey MSAs")

st.caption("Price-cut share is not present in the loaded datasets. Unsupported metrics appear as Not available, never zero.")

st.subheader("AI comparative analysis", icon=":material/auto_awesome:")
insight_key = (tuple(towns), tuple(msas))
if st.button("Generate comparative analysis", icon=":material/auto_awesome:", type="primary", key="compare_ai"):
    if towns:
        prompt = (f"Compare these New Jersey cities using city-level ZHVI and one- and five-year appreciation: {towns}. "
                  "Use actual dates and units. Do not substitute MSA metrics; state their city-level unavailability.")
    else:
        prompt = (f"Compare these New Jersey MSAs using for-sale inventory: {msas}. Use actual dates and units, "
                  "and do not substitute city-level ZHVI.")
    with st.status(":shimmer[Comparing markets]", type="compact") as status:
        result = get_agent_system().ask(prompt, st.session_state.insight_thread_id)
        st.session_state.comparison_insight = result
        st.session_state.comparison_insight_key = insight_key
        status.update(label="Comparative analysis ready", state="complete")
if st.session_state.comparison_insight_key == insight_key:
    insight_panel(st.session_state.comparison_insight)
else:
    st.caption("Generate an analysis after selecting markets. EstateIQ calls the existing validated agent workflow once.")

