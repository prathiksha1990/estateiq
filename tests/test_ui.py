import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from real_estate.database import SCHEMA
from real_estate.ui_chat import process_message
from real_estate.ui_components import format_value
from real_estate.ui_data import (appreciation_series, available_locations, comparison_table, filter_period,
                                 latest_record, metric_series, transparency_rows)


@pytest.fixture
def ui_db(tmp_path):
    path = tmp_path / "ui.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.executemany("""INSERT INTO metrics
          (region_id,region_name,state,geography,date,metric_name,value,unit,source_filename,metadata_json)
          VALUES(?,?,?,?,?,?,?,?,?,?)""", [
            ("1", "Alpha", "NJ", "city", "2020-01-31", "zhvi", 100.0, "USD", "zhvi.csv", "{}"),
            ("1", "Alpha", "NJ", "city", "2024-01-31", "zhvi", 150.0, "USD", "zhvi.csv", "{}"),
            ("1", "Alpha", "NJ", "city", "2025-01-31", "zhvi", 165.0, "USD", "zhvi.csv", "{}"),
            ("2", "Beta", "NJ", "city", "2025-01-31", "zhvi", None, "USD", "zhvi.csv", "{}"),
            ("10", "Trenton, NJ", "NJ", "msa", "2024-01-31", "for_sale_inventory", 25.0, "homes", "inventory.csv", "{}"),
            ("10", "Trenton, NJ", "NJ", "msa", "2025-01-31", "for_sale_inventory", 30.0, "homes", "inventory.csv", "{}"),
            ("10", "Trenton, NJ", "NJ", "msa", "2025-01-31", "median_sale_price", 400000.0, "USD", "price.csv", "{}"),
        ])
        connection.executemany("""INSERT INTO datasets
          (source_filename,metric_name,description,unit,geography_levels,populated_value_count,date_start,date_end)
          VALUES(?,?,?,?,?,?,?,?)""", [
            ("zhvi.csv", "zhvi", "ZHVI", "USD", '["city"]', 3, "2020-01-31", "2025-01-31"),
            ("inventory.csv", "for_sale_inventory", "Inventory", "homes", '["msa"]', 2, "2024-01-31", "2025-01-31"),
            ("price.csv", "median_sale_price", "Price", "USD", '["msa"]', 1, "2025-01-31", "2025-01-31"),
        ])
    return path


def test_database_to_ui_series_dates_units_and_period(ui_db):
    frame = metric_series(ui_db, "Alpha", "zhvi", "city")
    assert pd.api.types.is_datetime64_any_dtype(frame.date)
    assert set(frame.unit) == {"USD"}
    assert latest_record(frame) == {"value": 165.0, "date": "2025-01-31", "unit": "USD", "source_filename": "zhvi.csv"}
    assert len(filter_period(frame, 1)) == 2
    assert appreciation_series(frame, 1).iloc[-1]["value"] == pytest.approx(10.0)
    assert appreciation_series(frame, 5).iloc[-1]["value"] == pytest.approx(65.0)


def test_missing_metrics_and_geographic_separation(ui_db):
    assert metric_series(ui_db, "Alpha", "for_sale_inventory", "city").empty
    city = comparison_table(ui_db, ["Alpha"], "city").iloc[0]
    assert city["For-sale inventory"] is None
    assert city["Price-cut share"] is None
    msa = comparison_table(ui_db, ["Trenton, NJ"], "msa").iloc[0]
    assert msa["Typical home value"] is None
    assert msa["For-sale inventory"] == 30.0
    assert msa["Median sale price"] == 400000.0


def test_town_selection_and_transparency(ui_db):
    assert available_locations(ui_db, "city") == ["Alpha", "Beta"]
    assert available_locations(ui_db, "msa") == ["Trenton, NJ"]
    transparency = transparency_rows(ui_db)
    assert set(transparency["Coverage"]) == {"city", "msa"}
    assert "2025-01-31" in set(transparency["Latest observation"])


def test_not_available_formatting():
    assert format_value(None, "Median sale price") == "Not available"
    assert format_value(float("nan"), "Price-cut share") == "Not available"


class FakeAgent:
    def __init__(self):
        self.calls = []

    def ask(self, text, thread_id):
        self.calls.append(("ask", text, thread_id))
        return {"__interrupt__": [SimpleNamespace(value={"question": "Which town?"})]}

    def resume(self, text, thread_id):
        self.calls.append(("resume", text, thread_id))
        return {"final_answer": "Alpha result", "validation": {"valid": True}}


def test_conversation_thread_persistence_and_interruption():
    state = {"thread_id": "stable-thread", "messages": [], "pending_clarification": False}
    agent = FakeAgent()
    first = process_message(agent, state, "How is the market?")
    assert first["status"] == "clarification"
    assert state["pending_clarification"] is True
    second = process_message(agent, state, "Alpha")
    assert second["status"] == "complete"
    assert agent.calls == [("ask", "How is the market?", "stable-thread"),
                           ("resume", "Alpha", "stable-thread")]
    assert state["last_agent_state"]["final_answer"] == "Alpha result"


def test_agent_error_is_visible():
    class BrokenAgent:
        def ask(self, text, thread_id):
            raise RuntimeError("provider unavailable")
    state = {"thread_id": "x", "messages": [], "pending_clarification": False}
    outcome = process_message(BrokenAgent(), state, "question")
    assert outcome["status"] == "error"
    assert "provider unavailable" in outcome["message"]
    assert state["messages"][-1]["error"] is True


def test_estateiq_navigation_and_filter_persistence():
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    app = AppTest.from_file(app_path, default_timeout=20).run()
    assert not app.exception
    app.selectbox[0].set_value("Princeton")
    app.selectbox[2].set_value("10 years")
    app.run()
    app.switch_page("app_pages/ai_market_analyst.py").run()
    assert not app.exception
    app.switch_page("app_pages/compare_markets.py").run()
    assert not app.exception
    app.switch_page("app_pages/agent_activity.py").run()
    assert not app.exception
    app.switch_page("app_pages/market_overview.py").run()
    assert app.session_state["selected_town"] == "Princeton"
    assert app.session_state["selected_period"] == "10 years"
    assert not app.exception
