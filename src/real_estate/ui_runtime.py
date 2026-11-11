"""Shared EstateIQ runtime, cache, and per-session state helpers."""

import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from .agent_graph import RealEstateAgentSystem
from .ui_data import (available_locations, comparison_table, comparison_trends,
                      metric_catalog, metric_series, transparency_rows)

DATABASE = Path("data/processed/real_estate.db")
CHECKPOINTS = Path("data/processed/conversations.db")


def initialize_session() -> None:
    defaults = {
        "thread_id": str(uuid.uuid4()), "insight_thread_id": str(uuid.uuid4()),
        "messages": [], "pending_clarification": False, "last_agent_state": None,
        "selected_town": "Westfield", "selected_msa": "Trenton, NJ", "selected_period": "5 years",
        "comparison_towns": ["Westfield", "Summit"],
        "comparison_msas": ["Trenton, NJ", "Atlantic City, NJ"],
        "overview_insight": None, "overview_insight_key": None,
        "comparison_insight": None, "comparison_insight_key": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_resource(max_entries=1)
def get_agent_system() -> RealEstateAgentSystem:
    return RealEstateAgentSystem(DATABASE, CHECKPOINTS)


@st.cache_data(ttl="5m", max_entries=12)
def cached_locations(geography: str) -> list[str]:
    return available_locations(DATABASE, geography)


@st.cache_data(ttl="5m", max_entries=8)
def cached_catalog() -> pd.DataFrame:
    return metric_catalog(DATABASE)


@st.cache_data(ttl="5m", max_entries=128)
def cached_series(region: str, metric: str, geography: str) -> pd.DataFrame:
    return metric_series(DATABASE, region, metric, geography)


@st.cache_data(ttl="5m", max_entries=32)
def cached_comparison(regions: tuple[str, ...], geography: str) -> pd.DataFrame:
    return comparison_table(DATABASE, list(regions), geography)


@st.cache_data(ttl="5m", max_entries=64)
def cached_comparison_trends(regions: tuple[str, ...], metric: str,
                             geography: str, years: int | None) -> pd.DataFrame:
    return comparison_trends(DATABASE, list(regions), metric, geography, years)


@st.cache_data(ttl="5m", max_entries=4)
def cached_transparency() -> pd.DataFrame:
    return transparency_rows(DATABASE)


def reset_conversation() -> None:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.pending_clarification = False
    st.session_state.last_agent_state = None


def period_years(label: str) -> int | None:
    return {"1 year": 1, "5 years": 5, "10 years": 10, "All available": None}[label]
