import argparse
import json
import logging
from pathlib import Path

from .ingestion import ingest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Zillow CSVs for New Jersey")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--database", type=Path, default=Path("data/processed/real_estate.db"))
    parser.add_argument("--report", type=Path, default=Path("data/processed/data_quality_report.json"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s %(message)s")
    report = ingest(args.raw_dir, args.database, args.report)
    print(json.dumps({"database": report["database"], "loaded": len(report["loaded"]),
                      "missing_optional_metrics": report["missing_optional_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
