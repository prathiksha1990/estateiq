"""Reusable Streamlit presentation components."""

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from .ui_data import METRIC_LABELS


def format_value(value, kind: str) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    if kind in {"Typical home value", "Median sale price"}:
        return f"${value:,.0f}"
    if "appreciation" in kind.lower() or kind == "Price-cut share":
        return f"{value:,.2f}%"
    if kind in {"For-sale inventory", "Median days to pending"}:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def line_chart(frame: pd.DataFrame, title: str, y_title: str, color: str | None = None,
               alt: str | None = None):
    if frame.empty:
        st.info("Not available for the selected location, geography, and period.")
        return
    figure = px.line(frame, x="date", y="value", color=color, title=title,
                     labels={"date": "Date", "value": y_title, "region_name": "Location"})
    figure.update_layout(
        hovermode="x unified", legend_title_text="Location", height=390,
        margin=dict(l=12, r=12, t=45 if title else 15, b=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#64748B"),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(gridcolor="#E2E8F0", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    figure.update_traces(connectgaps=False, line=dict(width=2.5))
    st.plotly_chart(figure, width="stretch", alt=alt or title or f"Time series of {y_title}")


def metric_card(label: str, value: str, delta=None, delta_description: str | None = None,
                observation_date: str | None = None, chart_data: list | None = None):
    if delta is not None and not pd.isna(delta):
        rendered_delta = f"{float(delta):+.2f}%"
    else:
        rendered_delta = None
    st.metric(
        label, value, rendered_delta,
        delta_description=delta_description,
        border=True,
        height="stretch",
        chart_data=chart_data or None,
        chart_type="line",
        help=f"Latest observation: {observation_date}" if observation_date else "No observation available",
    )


def comparison_display(frame: pd.DataFrame):
    display = frame.copy()
    for column in display.columns:
        if column not in {"Location", "Geography"} and not column.endswith("date"):
            display[column] = display[column].apply(lambda value: format_value(value, column))
        elif column.endswith("date"):
            display[column] = display[column].fillna("Not available")
    st.dataframe(display, hide_index=True, width="stretch",
                 alt="Sortable market comparison table with dates and unavailable metrics")


def insight_panel(state: dict[str, Any] | None):
    if not state:
        return
    if state.get("error"):
        st.error(state["error"], icon=":material/error:")
        return
    validation = state.get("validation", {})
    with st.container(border=True):
        if validation.get("valid"):
            st.badge("Validated", icon=":material/verified:", color="green")
        else:
            st.badge("Validation warning", icon=":material/warning:", color="orange")
        st.markdown(state.get("final_answer", "No analysis was produced."))


def render_supporting_data(state: dict[str, Any] | None):
    if not state:
        return
    results = state.get("analysis", {}).get("results", [])
    rows = []
    for result in results:
        for record in result.get("records", []):
            if all(key in record for key in ("region_name", "metric_name", "date", "value")):
                rows.append({
                    "Location": record["region_name"], "Metric": metric_label(record["metric_name"]),
                    "Date": record["date"], "Value": record["value"], "Unit": record.get("unit"),
                    "Geography": record.get("geography") or result.get("geography"),
                })
    if rows:
        with st.expander("Supporting data", icon=":material/table_chart:"):
            st.dataframe(pd.DataFrame(rows).tail(50), hide_index=True, width="stretch",
                         alt="Retrieved database observations supporting the AI answer")


def execution_details(state: dict[str, Any] | None, expanded: bool = False):
    with st.expander("Agent execution details", expanded=expanded, icon=":material/account_tree:"):
        if not state:
            st.caption("Run an AI research question to see execution metadata.")
            return
        agents = []
        if state.get("plan"): agents.append("Research Planner")
        if state.get("analysis"): agents.append("Data Analysis Agent")
        if state.get("report"): agents.append("Market Intelligence Agent")
        if state.get("validation"): agents.append("Answer Validation Agent")
        st.markdown("**Agents executed**  \n" + (" → ".join(agents) or "None"))
        results = state.get("analysis", {}).get("results", [])
        tools = [result.get("tool") for result in results if result.get("tool")]
        st.markdown("**Tools invoked**  \n" + (", ".join(tools) or "None"))
        validation = state.get("validation", {})
        if validation.get("valid"):
            st.badge("Validation passed", icon=":material/verified:", color="green")
        else:
            st.badge("Validation not passed / not run", icon=":material/warning:", color="orange")
        st.markdown(f"**Retry count**  \n{state.get('retry_count', 0)}")
        sources = sorted({result.get("source") for result in results if result.get("source")})
        st.markdown("**Data sources**  \n" + (", ".join(sources) or "None"))
        warnings = list(state.get("analysis", {}).get("errors", [])) + list(validation.get("errors", []))
        if state.get("error"): warnings.append(state["error"])
        st.markdown("**Errors or warnings**  \n" + ("; ".join(warnings) if warnings else "None"))


def metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric.replace("_", " ").title())

