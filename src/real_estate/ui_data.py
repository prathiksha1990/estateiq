"""Read-only, deterministic data preparation for the Streamlit UI."""

import json
import sqlite3
from pathlib import Path

import pandas as pd

from .queries import (calculate_home_value_appreciation, compare_towns,
                      list_locations, list_metrics)

METRIC_LABELS = {
    "zhvi": "Zillow Home Value Index (ZHVI)",
    "for_sale_inventory": "For-sale inventory",
    "median_sale_price": "Median sale price",
    "sales_count": "Sales count",
    "median_days_to_pending": "Median days to pending",
    "market_heat_index": "Market heat index",
    "price_cut_share": "Price-cut share",
}


def available_locations(database: str | Path, geography: str) -> list[str]:
    frame = list_locations(database, geography=geography)
    return frame["region_name"].drop_duplicates().sort_values().tolist()


def metric_catalog(database: str | Path) -> pd.DataFrame:
    frame = list_metrics(database).copy()
    frame["label"] = frame["metric_name"].map(METRIC_LABELS).fillna(frame["metric_name"])
    frame["geographic_coverage"] = frame["geography_levels"].apply(
        lambda value: ", ".join(json.loads(value)) if isinstance(value, str) else "Unknown")
    return frame


def metric_series(database: str | Path, region_name: str, metric_name: str,
                  geography: str, start_date: str | None = None,
                  end_date: str | None = None) -> pd.DataFrame:
    """Retrieve one supported series with fixed parameterized SQL."""
    clauses = ["region_name = ? COLLATE NOCASE", "metric_name = ?", "geography = ?"]
    params: list[object] = [region_name, metric_name, geography]
    if start_date:
        clauses.append("date >= ?"); params.append(start_date)
    if end_date:
        clauses.append("date <= ?"); params.append(end_date)
    uri = f"file:{Path(database).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        frame = pd.read_sql_query(
            f"""SELECT region_id, region_name, geography, date, metric_name, value, unit,
                       source_filename
                FROM metrics WHERE {' AND '.join(clauses)} ORDER BY date""",
            connection, params=params)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def filter_period(frame: pd.DataFrame, years: int | None, end_date=None) -> pd.DataFrame:
    if frame.empty or years is None:
        return frame.copy()
    end = pd.Timestamp(end_date) if end_date is not None else frame["date"].max()
    return frame[frame["date"] >= end - pd.DateOffset(years=years)].copy()


def latest_record(frame: pd.DataFrame) -> dict | None:
    populated = frame.dropna(subset=["value"]) if not frame.empty else frame
    if populated.empty:
        return None
    row = populated.sort_values("date").iloc[-1]
    return {"value": float(row["value"]), "date": pd.Timestamp(row["date"]).date().isoformat(),
            "unit": row["unit"], "source_filename": row.get("source_filename")}


def appreciation_series(frame: pd.DataFrame, years: int) -> pd.DataFrame:
    """Calculate point-in-time appreciation against the same month N years ago."""
    if frame.empty:
        return pd.DataFrame(columns=["date", "value"])
    current = frame[["date", "value"]].dropna().copy().sort_values("date")
    prior = current.rename(columns={"date": "prior_date", "value": "prior_value"})
    prior["date"] = prior["prior_date"] + pd.DateOffset(years=years)
    merged = current.merge(prior[["date", "prior_value"]], on="date", how="left")
    merged["value"] = (merged["value"] / merged["prior_value"] - 1) * 100
    return merged[["date", "value"]].dropna()


def city_appreciation(database: str | Path, town: str) -> dict:
    result = calculate_home_value_appreciation(database, town)
    return result or {"region_name": town, "as_of_date": None, "latest_value": None,
                      "one_year_pct": None, "five_year_pct": None}


def comparison_table(database: str | Path, regions: list[str], geography: str) -> pd.DataFrame:
    columns = ["Location", "Geography", "Typical home value", "ZHVI date",
               "1-year appreciation", "5-year appreciation", "For-sale inventory",
               "Inventory date", "Median sale price", "Sale-price date",
               "Median days to pending", "Pending date", "Price-cut share"]
    rows = []
    for region in regions[:3]:
        row = {column: None for column in columns}
        row.update({"Location": region, "Geography": geography.upper(), "Price-cut share": None})
        if geography == "city":
            appreciation = city_appreciation(database, region)
            row.update({"Typical home value": appreciation.get("latest_value"),
                        "ZHVI date": appreciation.get("as_of_date"),
                        "1-year appreciation": appreciation.get("one_year_pct"),
                        "5-year appreciation": appreciation.get("five_year_pct")})
        else:
            for metric, value_col, date_col in (
                ("for_sale_inventory", "For-sale inventory", "Inventory date"),
                ("median_sale_price", "Median sale price", "Sale-price date"),
                ("median_days_to_pending", "Median days to pending", "Pending date"),
            ):
                latest = latest_record(metric_series(database, region, metric, geography))
                if latest:
                    row[value_col], row[date_col] = latest["value"], latest["date"]
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def comparison_trends(database: str | Path, regions: list[str], metric_name: str,
                      geography: str, years: int | None = None) -> pd.DataFrame:
    frame = compare_towns(database, metric_name, regions[:3], geography)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return filter_period(frame, years).dropna(subset=["value"])


def transparency_rows(database: str | Path) -> pd.DataFrame:
    frame = metric_catalog(database)
    return frame[["label", "unit", "geographic_coverage", "date_start", "date_end",
                  "populated_value_count"]].rename(columns={
        "label": "Dataset metric", "unit": "Unit", "geographic_coverage": "Coverage",
        "date_start": "First observation", "date_end": "Latest observation",
        "populated_value_count": "Populated observations",
    })

