import sqlite3
from pathlib import Path

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY,
  region_id TEXT NOT NULL,
  region_name TEXT NOT NULL,
  state TEXT NOT NULL,
  geography TEXT NOT NULL,
  date TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  value REAL,
  unit TEXT NOT NULL,
  source_filename TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(region_id, geography, date, metric_name, source_filename)
);
CREATE TABLE IF NOT EXISTS datasets (
  source_filename TEXT PRIMARY KEY,
  metric_name TEXT NOT NULL,
  description TEXT NOT NULL,
  unit TEXT NOT NULL,
  state_column TEXT,
  geography_levels TEXT,
  source_row_count INTEGER,
  nj_region_count INTEGER,
  normalized_row_count INTEGER,
  populated_value_count INTEGER,
  date_start TEXT,
  date_end TEXT,
  missing_value_count INTEGER,
  issue_summary_json TEXT,
  loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_metrics_geography ON metrics(geography, region_name);
CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date);
CREATE INDEX IF NOT EXISTS idx_metrics_metric ON metrics(metric_name, date);
CREATE INDEX IF NOT EXISTS idx_metrics_region_metric_date ON metrics(region_id, geography, metric_name, date);
"""


def initialize_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


def replace_dataset(connection: sqlite3.Connection, source: str, frame: pd.DataFrame, metadata: dict) -> None:
    connection.execute("DELETE FROM metrics WHERE source_filename = ?", (source,))
    out = frame.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_sql("metrics", connection, if_exists="append", index=False)
    columns = list(metadata)
    placeholders = ",".join("?" for _ in columns)
    connection.execute(f"INSERT OR REPLACE INTO datasets ({','.join(columns)}) VALUES ({placeholders})",
                       [metadata[c] for c in columns])
    connection.commit()

