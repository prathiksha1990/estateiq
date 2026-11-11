import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from real_estate.config import DatasetSpec
from real_estate.ingestion import ingest
from real_estate.queries import (calculate_home_value_appreciation, compare_towns,
                                 get_historical_home_values, get_latest_observation,
                                 list_locations, list_metrics)
from real_estate.transform import transform_file


@pytest.fixture
def raw_dir(tmp_path):
    folder = tmp_path / "raw"
    folder.mkdir()
    pd.DataFrame({
        "RegionID": [1, 2, 3], "SizeRank": [1, 2, 3],
        "RegionName": ["Alpha", "Beta", "Elsewhere"], "RegionType": ["city"] * 3,
        "StateName": ["NJ", "NJ", "NY"], "State": ["NJ", "NJ", "NY"],
        "Metro": ["A Metro", None, "Other"], "CountyName": ["A County", "B County", "Other"],
        "2019-01-31": [100.0, None, 900.0], "2020-01-31": [110.0, 200.0, 999.0],
        "2024-01-31": [150.0, 250.0, 1200.0], "2025-01-31": [165.0, 275.0, 1300.0],
    }).to_csv(folder / "zhvi_home_values.csv", index=False)
    pd.DataFrame({
        "RegionID": [10, 11], "RegionName": ["Trenton, NJ", "Albany, NY"],
        "RegionType": ["msa", "msa"], "StateName": ["NJ", "NY"],
        "2025-01-31": [30, 40], "2025-02-28": [None, 42],
    }).to_csv(folder / "sales_count_monthly.csv", index=False)
    return folder


@pytest.fixture
def database(tmp_path, raw_dir):
    path = tmp_path / "real_estate.db"
    ingest(raw_dir, path, tmp_path / "quality.json")
    return path


def test_transform_filters_nj_and_preserves_missing(raw_dir):
    frame, profile = transform_file(raw_dir / "zhvi_home_values.csv", DatasetSpec("zhvi", "USD", "test"))
    assert set(frame.region_name) == {"Alpha", "Beta"}
    assert len(frame) == 8
    assert frame.value.isna().sum() == 1
    assert profile["state_column"] == "State"
    assert profile["geographies"] == ["city"]
    assert '"CountyName": "A County"' in frame.iloc[0].metadata_json


def test_validation_detects_bad_values_and_duplicates(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"RegionID": [1, 1], "RegionName": ["A", "A"], "RegionType": ["city", "city"],
                  "StateName": ["NJ", "NJ"], "2025-01-31": ["bad", -1]}).to_csv(path, index=False)
    _, profile = transform_file(path, DatasetSpec("metric", "count", "test"))
    assert profile["issues"]["nonnumeric_values"] == 1
    assert profile["issues"]["negative_values"] == 1
    assert profile["issues"]["duplicate_records"] == 2


def test_ingestion_and_metadata(database):
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 10
        assert con.execute("SELECT value FROM metrics WHERE region_name='Beta' AND date='2019-01-31'").fetchone()[0] is None
        assert con.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 2
    assert set(list_metrics(database).metric_name) == {"zhvi", "sales_count"}
    assert set(list_locations(database, geography="city").region_name) == {"Alpha", "Beta"}


def test_queries_and_appreciation(database):
    history = get_historical_home_values(database, "alpha")
    assert len(history) == 4
    compared = compare_towns(database, "zhvi", ["Alpha", "Beta"])
    assert len(compared) == 8
    result = calculate_home_value_appreciation(database, "Alpha")
    assert result["one_year_pct"] == pytest.approx(10.0)
    assert result["five_year_pct"] == pytest.approx(50.0)
    latest = get_latest_observation(database, "zhvi", geography="city")
    assert set(latest.region_name) == {"Alpha", "Beta"}
    assert set(latest.date) == {"2025-01-31"}


def test_missing_town_and_missing_optional_files(database):
    assert get_historical_home_values(database, "Missing").empty
    assert calculate_home_value_appreciation(database, "Missing") is None
    report_path = database.parent / "report2.json"
    report = ingest(database.parent / "does-not-exist", database.parent / "empty.db", report_path)
    assert report["loaded"] == []
    assert "zhvi" in report["missing_optional_metrics"]

