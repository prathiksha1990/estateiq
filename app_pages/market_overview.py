import streamlit as st

from real_estate.ui_components import format_value, insight_panel, line_chart, metric_card
from real_estate.ui_data import appreciation_series, city_appreciation, filter_period, latest_record
from real_estate.ui_runtime import (DATABASE, cached_locations, cached_series,
                                    get_agent_system, period_years)

st.title("Market overview")
st.caption("Track home values and market activity across New Jersey with transparent geographic coverage.")

city_locations = cached_locations("city")
msa_locations = cached_locations("msa")
if st.session_state.selected_town not in city_locations:
    st.session_state.selected_town = city_locations[0]
if st.session_state.selected_msa not in msa_locations:
    st.session_state.selected_msa = msa_locations[0]

with st.container(border=True):
    controls = st.columns([2, 2, 1.4], vertical_alignment="bottom")
    town = controls[0].selectbox("Town", city_locations, key="selected_town", persist_state="session")
    msa = controls[1].selectbox("Market area for activity metrics", msa_locations,
                               key="selected_msa", persist_state="session",
                               help="Inventory and days-to-pending are available only at MSA level.")
    period = controls[2].selectbox("Time period", ["1 year", "5 years", "10 years", "All available"],
                                  key="selected_period", persist_state="session")

years = period_years(period)
zhvi_full = cached_series(town, "zhvi", "city")
zhvi = filter_period(zhvi_full, years)
inventory = filter_period(cached_series(msa, "for_sale_inventory", "msa"), years)
pending = cached_series(msa, "median_days_to_pending", "msa")
appreciation = city_appreciation(DATABASE, town)
zhvi_latest = latest_record(zhvi_full)
inventory_latest = latest_record(inventory)
pending_latest = latest_record(pending)

with st.container(horizontal=True):
    metric_card("Typical home value", format_value(zhvi_latest["value"] if zhvi_latest else None, "Typical home value"),
                appreciation.get("one_year_pct"), "1-year ZHVI change", zhvi_latest["date"] if zhvi_latest else None,
                zhvi_full["value"].dropna().tail(18).tolist())
    metric_card("Five-year appreciation", format_value(appreciation.get("five_year_pct"), "5-year appreciation"),
                None, None, appreciation.get("as_of_date"))
    metric_card("For-sale inventory", format_value(inventory_latest["value"] if inventory_latest else None, "For-sale inventory"),
                None, msa, inventory_latest["date"] if inventory_latest else None,
                inventory["value"].dropna().tail(18).tolist())
    metric_card("Days to pending", format_value(pending_latest["value"] if pending_latest else None, "Median days to pending"),
                None, msa, pending_latest["date"] if pending_latest else None)

chart_cols = st.columns([1.45, 1], gap="large")
with chart_cols[0]:
    with st.container(border=True):
        st.subheader("Historical home value", icon=":material/show_chart:")
        st.caption(f"{town} · Zillow Home Value Index · {period}")
        line_chart(zhvi, "", "ZHVI (USD)", alt=f"Historical ZHVI for {town}")
with chart_cols[1]:
    with st.container(border=True):
        st.subheader("Inventory trend", icon=":material/home_work:")
        st.caption(f"{msa} MSA · Active for-sale inventory · {period}")
        line_chart(inventory, "", "Homes", alt=f"For-sale inventory trend for {msa} MSA")

with st.container(border=True):
    st.subheader("Appreciation momentum", icon=":material/trending_up:")
    appreciation_cols = st.columns(2, gap="large")
    with appreciation_cols[0]:
        line_chart(appreciation_series(zhvi_full, 1), "Year-over-year appreciation", "Change (%)",
                   alt=f"Year-over-year ZHVI appreciation for {town}")
    with appreciation_cols[1]:
        line_chart(appreciation_series(zhvi_full, 5), "Five-year appreciation", "Change (%)",
                   alt=f"Five-year ZHVI appreciation for {town}")

st.subheader("AI market insight", icon=":material/auto_awesome:")
insight_key = (town, msa, period)
if st.button("Generate market insight", icon=":material/auto_awesome:", type="primary", key="overview_ai"):
    prompt = (f"Summarize the market for {town}, New Jersey using city-level ZHVI and its one- and five-year "
              "appreciation. Use actual observation dates, distinguish facts from interpretation, and state limitations. "
              f"Do not substitute MSA data; the dashboard separately displays activity for the selected {msa} MSA.")
    with st.status(":shimmer[Researching the market]", type="compact") as status:
        result = get_agent_system().ask(prompt, st.session_state.insight_thread_id)
        st.session_state.overview_insight = result
        st.session_state.overview_insight_key = insight_key
        status.update(label="Market insight ready", state="complete")
if st.session_state.overview_insight_key == insight_key:
    insight_panel(st.session_state.overview_insight)
else:
    st.caption("Generate an insight to interpret the selected market using the validated agent workflow.")

st.caption("Latest observations — " + " · ".join([
    f"ZHVI {zhvi_latest['date'] if zhvi_latest else 'Not available'}",
    f"Inventory {inventory_latest['date'] if inventory_latest else 'Not available'}",
    f"Days to pending {pending_latest['date'] if pending_latest else 'Not available'}",
]) + ". City and MSA metrics describe different geographic areas.")

