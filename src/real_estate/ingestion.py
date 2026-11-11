import json
import logging
from pathlib import Path

from .config import DATASETS, OPTIONAL_METRICS
from .database import initialize_database, replace_dataset
from .transform import inspect_schema, transform_file

LOGGER = logging.getLogger(__name__)


def ingest(raw_dir: Path, database_path: Path, report_path: Path | None = None) -> dict:
    raw_dir, database_path = Path(raw_dir), Path(database_path)
    available = {p.name: p for p in raw_dir.glob("*.csv")}
    selected = [(name, path, DATASETS[name]) for name, path in available.items() if name in DATASETS]
    unknown = sorted(set(available).difference(DATASETS))
    present_metrics = {spec.metric_name for _, _, spec in selected}
    report = {"database": str(database_path), "loaded": [],
              "missing_optional_metrics": sorted(set(OPTIONAL_METRICS) - present_metrics),
              "unrecognized_files": unknown}
    if not selected:
        LOGGER.warning("No recognized Zillow CSV files found in %s", raw_dir)
    connection = initialize_database(database_path)
    try:
        for name, path, spec in sorted(selected):
            schema = inspect_schema(path)
            LOGGER.info("Inspecting %s: %d columns; state=%s", name, len(schema["columns"]), schema["state_columns"])
            frame, profile = transform_file(path, spec)
            issue_summary = profile["issues"]
            valid_dates = frame["date"].dropna()
            metadata = {
                "source_filename": name, "metric_name": spec.metric_name,
                "description": spec.description, "unit": spec.unit,
                "state_column": profile["state_column"],
                "geography_levels": json.dumps(profile["geographies"]),
                "source_row_count": profile["raw_rows"], "nj_region_count": profile["nj_regions"],
                "normalized_row_count": len(frame), "populated_value_count": int(frame["value"].notna().sum()),
                "date_start": valid_dates.min().strftime("%Y-%m-%d") if len(valid_dates) else None,
                "date_end": valid_dates.max().strftime("%Y-%m-%d") if len(valid_dates) else None,
                "missing_value_count": issue_summary["missing_values"],
                "issue_summary_json": json.dumps(issue_summary, sort_keys=True),
            }
            replace_dataset(connection, name, frame, metadata)
            # Keep the persisted quality report concise; schema samples are
            # inspected before transformation but need not duplicate source data.
            item = {**metadata, "source_column_count": len(schema["columns"]),
                    "date_column_count": profile["date_columns"]}
            report["loaded"].append(item)
            LOGGER.info("Loaded %s: %d NJ regions, %d records", name, profile["nj_regions"], len(frame))
    finally:
        connection.close()
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report
