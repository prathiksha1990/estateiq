import json
import re
from pathlib import Path

import pandas as pd

from .config import DatasetSpec

DATE_COLUMN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STANDARD_COLUMNS = [
    "region_id", "region_name", "state", "geography", "date",
    "metric_name", "value", "unit", "source_filename", "metadata_json",
]


def inspect_schema(path: Path) -> dict:
    sample = pd.read_csv(path, nrows=5)
    date_columns = [c for c in sample.columns if DATE_COLUMN.fullmatch(str(c))]
    state_columns = [c for c in ("State", "StateName") if c in sample.columns]
    return {
        "columns": list(sample.columns), "date_columns": date_columns,
        "state_columns": state_columns,
        "sample_records": sample.head(2).to_dict(orient="records"),
    }


def _state_column(columns) -> str:
    # State is the postal abbreviation in detailed Zillow files; StateName is
    # the equivalent field in Zillow's region-level series.
    for candidate in ("State", "StateName"):
        if candidate in columns:
            return candidate
    raise ValueError("No State or StateName column found")


def transform_file(path: Path, spec: DatasetSpec) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(path, dtype={"RegionID": "string"})
    state_col = _state_column(raw.columns)
    state = raw[state_col].astype("string").str.strip().str.upper()
    nj = raw[state.isin(["NJ", "NEW JERSEY"])].copy()
    date_cols = [c for c in raw.columns if DATE_COLUMN.fullmatch(str(c))]
    if not date_cols:
        raise ValueError(f"{path.name}: no ISO date columns found")
    metadata_cols = [c for c in raw.columns if c not in date_cols]
    required = {"RegionID", "RegionName"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"{path.name}: missing required columns: {sorted(missing)}")

    long = nj.melt(id_vars=metadata_cols, value_vars=date_cols,
                   var_name="date_raw", value_name="value_raw")
    long["date"] = pd.to_datetime(long["date_raw"], errors="coerce")
    long["value"] = pd.to_numeric(long["value_raw"], errors="coerce")
    long["region_id"] = long["RegionID"].astype("string")
    long["region_name"] = long["RegionName"].astype("string")
    long["state"] = "NJ"
    long["geography"] = long.get("RegionType", pd.Series("unknown", index=long.index)).astype("string").str.lower()
    long["metric_name"] = spec.metric_name
    long["unit"] = spec.unit
    long["source_filename"] = path.name
    extra_cols = [c for c in metadata_cols if c not in {"RegionID", "RegionName", "RegionType", "State", "StateName"}]
    long["metadata_json"] = long[extra_cols].apply(
        lambda row: json.dumps({k: v for k, v in row.items() if pd.notna(v)}, default=str, sort_keys=True), axis=1
    ) if extra_cols else "{}"

    issues = {
        "missing_region_id": int(long["region_id"].isna().sum()),
        "missing_region_name": int(long["region_name"].isna().sum()),
        "invalid_dates": int(long["date"].isna().sum()),
        "nonnumeric_values": int((long["value_raw"].notna() & long["value"].isna()).sum()),
        "missing_values": int(long["value"].isna().sum()),
        "negative_values": int((long["value"] < 0).sum()) if spec.nonnegative else 0,
    }
    key = ["region_id", "geography", "date", "metric_name"]
    issues["duplicate_records"] = int(long.duplicated(key, keep=False).sum())
    return long[STANDARD_COLUMNS], {
        "state_column": state_col, "raw_rows": len(raw), "nj_regions": len(nj),
        "geographies": sorted(nj["RegionType"].dropna().astype(str).str.lower().unique().tolist()) if "RegionType" in nj else ["unknown"],
        "date_column_start": min(date_cols), "date_column_end": max(date_cols),
        "date_columns": len(date_cols), "issues": issues,
    }

