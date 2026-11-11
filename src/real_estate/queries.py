import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd


def _connect(database) -> sqlite3.Connection:
    return sqlite3.connect(Path(database))


def get_historical_home_values(database, town: str) -> pd.DataFrame:
    with _connect(database) as con:
        return pd.read_sql_query(
            """SELECT region_id, region_name, date, value, unit FROM metrics
               WHERE metric_name='zhvi' AND geography='city' AND region_name = ? COLLATE NOCASE
               ORDER BY date""", con, params=(town,))


def compare_towns(database, metric_name: str, towns: Iterable[str], geography: str = "city") -> pd.DataFrame:
    towns = list(towns)
    if not towns:
        return pd.DataFrame(columns=["region_id", "region_name", "geography", "date", "metric_name", "value", "unit"])
    marks = ",".join("?" for _ in towns)
    sql = f"""SELECT region_id, region_name, geography, date, metric_name, value, unit
              FROM metrics WHERE metric_name=? AND geography=?
              AND region_name COLLATE NOCASE IN ({marks}) ORDER BY date, region_name"""
    with _connect(database) as con:
        return pd.read_sql_query(sql, con, params=[metric_name, geography, *towns])


def compare_regions(database, metric_name: str, region_ids: Iterable[str], geography: str) -> pd.DataFrame:
    region_ids = list(region_ids)
    if not region_ids:
        return pd.DataFrame(columns=["region_id", "region_name", "geography", "date", "metric_name", "value", "unit"])
    marks = ",".join("?" for _ in region_ids)
    sql = f"""SELECT region_id, region_name, geography, date, metric_name, value, unit
              FROM metrics WHERE metric_name=? AND geography=? AND region_id IN ({marks})
              ORDER BY date, region_name"""
    with _connect(database) as con:
        return pd.read_sql_query(sql, con, params=[metric_name, geography, *region_ids])


def calculate_home_value_appreciation(database, town: str) -> dict | None:
    history = get_historical_home_values(database, town).dropna(subset=["value"])
    if history.empty:
        return None
    history["date"] = pd.to_datetime(history["date"])
    latest = history.iloc[-1]
    result = {"region_name": latest["region_name"], "as_of_date": latest["date"].date().isoformat(),
              "latest_value": float(latest["value"])}
    for years, label in ((1, "one_year_pct"), (5, "five_year_pct")):
        target = latest["date"] - pd.DateOffset(years=years)
        candidates = history[history["date"] <= target]
        if candidates.empty or float(candidates.iloc[-1]["value"]) == 0:
            result[label] = None
            result[label.replace("pct", "comparison_date")] = None
        else:
            prior = candidates.iloc[-1]
            result[label] = (float(latest["value"]) / float(prior["value"]) - 1) * 100
            result[label.replace("pct", "comparison_date")] = prior["date"].date().isoformat()
    return result


def get_latest_observation(database, metric_name: str, region_name: str | None = None,
                           geography: str | None = None) -> pd.DataFrame:
    clauses, params = ["metric_name=?", "value IS NOT NULL"], [metric_name]
    if region_name is not None:
        clauses.append("region_name = ? COLLATE NOCASE"); params.append(region_name)
    if geography is not None:
        clauses.append("geography=?"); params.append(geography)
    where = " AND ".join(clauses)
    sql = f"""SELECT region_id, region_name, geography, date, metric_name, value, unit
              FROM metrics m WHERE {where} AND date=(SELECT MAX(date) FROM metrics WHERE {where})
              ORDER BY geography, region_name"""
    with _connect(database) as con:
        return pd.read_sql_query(sql, con, params=params + params)


def get_latest_observation_by_region_id(database, metric_name: str, region_id: str,
                                        geography: str) -> pd.DataFrame:
    sql = """SELECT region_id, region_name, geography, date, metric_name, value, unit
             FROM metrics WHERE metric_name=? AND region_id=? AND geography=? AND value IS NOT NULL
             AND date=(SELECT MAX(date) FROM metrics WHERE metric_name=? AND region_id=?
                       AND geography=? AND value IS NOT NULL)
             ORDER BY region_name"""
    params = (metric_name, region_id, geography, metric_name, region_id, geography)
    with _connect(database) as con:
        return pd.read_sql_query(sql, con, params=params)


def list_locations(database, geography: str | None = None, metric_name: str | None = None) -> pd.DataFrame:
    clauses, params = [], []
    if geography: clauses.append("geography=?"); params.append(geography)
    if metric_name: clauses.append("metric_name=?"); params.append(metric_name)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect(database) as con:
        return pd.read_sql_query(f"SELECT DISTINCT region_id, region_name, state, geography FROM metrics {where} ORDER BY geography, region_name", con, params=params)


def list_metrics(database) -> pd.DataFrame:
    with _connect(database) as con:
        return pd.read_sql_query("SELECT metric_name, unit, geography_levels, date_start, date_end, populated_value_count FROM datasets ORDER BY metric_name", con)

