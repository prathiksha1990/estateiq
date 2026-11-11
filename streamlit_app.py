"""EstateIQ Streamlit entry point."""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from real_estate.ui_runtime import initialize_session

st.set_page_config(
    page_title="EstateIQ — NJ market intelligence",
    page_icon=":material/real_estate_agent:",
    layout="wide",
)

initialize_session()

with st.sidebar:
    st.title("EstateIQ", icon=":material/real_estate_agent:")
    st.caption("New Jersey market intelligence")

navigation = st.navigation(
    [
        st.Page("app_pages/market_overview.py", title="Market overview", icon=":material/space_dashboard:", default=True),
        st.Page("app_pages/ai_market_analyst.py", title="AI market analyst", icon=":material/smart_toy:"),
        st.Page("app_pages/compare_markets.py", title="Compare markets", icon=":material/compare_arrows:"),
        st.Page("app_pages/agent_activity.py", title="Agent activity & data", icon=":material/account_tree:"),
    ],
    position="sidebar",
)

with st.sidebar:
    st.caption("Zillow Research data · Local SQLite · Validated AI")

navigation.run()
