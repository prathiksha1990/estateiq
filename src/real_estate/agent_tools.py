import json
from itertools import combinations
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from langsmith import traceable
from pydantic import BaseModel, Field
import pandas as pd

from .agent_models import ToolResult
from .queries import (calculate_home_value_appreciation, compare_regions, compare_towns,
                      get_historical_home_values, get_latest_observation, get_latest_observation_by_region_id,
                      list_locations, list_metrics)


class NoArgs(BaseModel):
    pass


class LocationsArgs(BaseModel):
    geography: str | None = None
    metric_name: str | None = None


class TownArgs(BaseModel):
    town: str


class CompareArgs(BaseModel):
    metric_name: str
    towns: list[str]
    geography: str
    start_date: str | None = None
    end_date: str | None = None


class LatestArgs(BaseModel):
    metric_name: str
    region_name: str | None = None
    geography: str | None = None


def _records(frame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


class RealEstateToolkit:
    """A fixed, read-only facade over Phase 1 query functions."""

    def __init__(self, database: str | Path):
        self.database = Path(database)

    def _guard(self) -> None:
        if not self.database.is_file():
            raise FileNotFoundError(f"Database not found: {self.database}")

    def _metric_support(self, metric_name: str, geography: str | None) -> tuple[bool, str]:
        frame = list_metrics(self.database)
        match = frame[frame.metric_name == metric_name]
        if match.empty:
            return False, f"Metric '{metric_name}' is not available. No substitute was used."
        levels = json.loads(str(match.iloc[0].geography_levels))
        if geography and geography not in levels:
            return False, (f"Metric '{metric_name}' is not available at the {geography} level; "
                           f"supported geography: {', '.join(levels)}. No substitute was used.")
        return True, ""

    def resolve_locations(self, names: list[str], geography: str) -> tuple[list[dict], list[str], dict[str, list[str]]]:
        records = self.available_locations(geography, None)["records"]
        resolved, missing, ambiguous = [], [], {}
        for requested in names:
            matches = [record for record in records if str(record["region_id"]).casefold() == requested.casefold()]
            if not matches:
                matches = [record for record in records if record["region_name"].casefold() == requested.casefold()]
            if not matches:
                matches = [record for record in records
                           if record["region_name"].split(",")[0].casefold() == requested.casefold()]
            if len(matches) == 1:
                resolved.append(matches[0])
            elif len(matches) > 1:
                ambiguous[requested] = [record["region_name"] for record in matches]
            else:
                missing.append(requested)
        return resolved, missing, ambiguous

    @traceable(name="list_available_metrics", run_type="tool")
    def available_metrics(self) -> dict:
        self._guard()
        frame = list_metrics(self.database)
        return ToolResult(tool="list_available_metrics", status="ok", records=_records(frame)).model_dump()

    @traceable(name="list_available_locations", run_type="tool")
    def available_locations(self, geography: str | None = None, metric_name: str | None = None) -> dict:
        self._guard()
        frame = list_locations(self.database, geography, metric_name)
        return ToolResult(tool="list_available_locations", status="ok", metric=metric_name,
                          geography=geography, records=_records(frame)).model_dump()

    @traceable(name="get_home_value_trend", run_type="tool")
    def home_value_trend(self, town: str) -> dict:
        self._guard()
        frame = get_historical_home_values(self.database, town)
        if frame.empty:
            return ToolResult(tool="get_home_value_trend", status="unavailable", metric="zhvi", unit="USD",
                              geography="city", message=f"No city-level ZHVI data for {town}.").model_dump()
        populated = frame.dropna(subset=["value"])
        return ToolResult(tool="get_home_value_trend", status="ok", metric="zhvi", unit="USD", geography="city",
                          date_start=frame.date.min(), date_end=frame.date.max(),
                          missing_observations=int(frame.value.isna().sum()), records=_records(populated)).model_dump()

    @traceable(name="compare_markets", run_type="tool")
    def compare(self, metric_name: str, towns: list[str], geography: str,
                start_date: str | None = None, end_date: str | None = None) -> dict:
        self._guard()
        supported, message = self._metric_support(metric_name, geography)
        if not supported:
            return ToolResult(tool="compare_markets", status="unavailable", metric=metric_name,
                              geography=geography, message=message).model_dump()
        resolved, missing, ambiguous = self.resolve_locations(towns, geography)
        if ambiguous:
            return ToolResult(tool="compare_markets", status="unavailable", metric=metric_name,
                              geography=geography, message=f"Ambiguous locations: {ambiguous}.").model_dump()
        if missing:
            return ToolResult(tool="compare_markets", status="unavailable", metric=metric_name,
                              geography=geography, message=f"Unavailable at {geography} level: {missing}.").model_dump()
        region_ids = [record["region_id"] for record in resolved]
        frame = compare_regions(self.database, metric_name, region_ids, geography)
        if start_date: frame = frame[frame.date >= start_date]
        if end_date: frame = frame[frame.date <= end_date]
        if frame.empty and (start_date or end_date):
            profile = list_metrics(self.database)
            profile = profile[profile.metric_name == metric_name].iloc[0]
            return ToolResult(tool="compare_markets", status="unavailable", metric=metric_name,
                              geography=geography, region_ids=region_ids,
                              message=(f"No observations in requested range {start_date or 'beginning'} to "
                                       f"{end_date or 'latest'}; available range is "
                                       f"{profile.date_start} to {profile.date_end}.")).model_dump()
        found = {x.casefold() for x in frame.region_name.unique()} if not frame.empty else set()
        resolved_names = [record["region_name"] for record in resolved]
        missing = [x for x in resolved_names if x.casefold() not in found]
        if frame.empty or missing:
            return ToolResult(tool="compare_markets", status="unavailable", metric=metric_name,
                              geography=geography, message=f"Unavailable at {geography} level: {missing or towns}.").model_dump()
        unit = str(frame.unit.iloc[0])
        populated = frame.dropna(subset=["value"])
        calculations = []
        latest_by_region = {}
        for region_name, group in populated.groupby("region_name"):
            group = group.copy()
            group["parsed_date"] = pd.to_datetime(group["date"])
            group = group.sort_values("parsed_date")
            latest = group.iloc[-1]
            latest_by_region[region_name] = float(latest["value"])
            summary = {"calculation": "region_change", "region_name": region_name,
                       "metric_name": metric_name, "geography": geography, "unit": unit,
                       "latest_date": latest["date"], "latest_value": float(latest["value"])}
            for years in (1, 5):
                target = latest["parsed_date"] - pd.DateOffset(years=years)
                candidates = group[group["parsed_date"] <= target]
                prior = candidates.iloc[-1] if not candidates.empty else None
                summary[f"{years}_year_comparison_date"] = prior["date"] if prior is not None else None
                summary[f"{years}_year_pct"] = ((float(latest["value"]) / float(prior["value"]) - 1) * 100
                                                  if prior is not None and float(prior["value"]) != 0 else None)
            calculations.append(summary)
        for left, right in combinations(sorted(latest_by_region), 2):
            calculations.append({"calculation": "latest_value_difference", "left_region": left,
                                 "right_region": right, "metric_name": metric_name,
                                 "geography": geography, "unit": unit,
                                 "left_minus_right": latest_by_region[left] - latest_by_region[right]})
        return ToolResult(tool="compare_markets", status="ok", metric=metric_name, unit=unit, geography=geography,
                          region_ids=region_ids,
                          date_start=frame.date.min(), date_end=frame.date.max(),
                          missing_observations=int(frame.value.isna().sum()), records=_records(populated),
                          calculations=calculations).model_dump()

    @traceable(name="calculate_appreciation", run_type="tool")
    def appreciation(self, town: str) -> dict:
        self._guard()
        result = calculate_home_value_appreciation(self.database, town)
        if result is None:
            return ToolResult(tool="calculate_appreciation", status="unavailable", metric="zhvi", unit="percent",
                              geography="city", message=f"No appreciation history for {town}.").model_dump()
        insufficient = result.get("one_year_pct") is None or result.get("five_year_pct") is None
        return ToolResult(tool="calculate_appreciation", status="unavailable" if insufficient else "ok",
                          metric="zhvi_appreciation", unit="percent", geography="city",
                          date_end=result["as_of_date"], records=[result],
                          message="Insufficient one- or five-year history." if insufficient else None).model_dump()

    @traceable(name="get_latest_market_metric", run_type="tool")
    def latest(self, metric_name: str, region_name: str | None = None,
               geography: str | None = None) -> dict:
        self._guard()
        supported, message = self._metric_support(metric_name, geography)
        if not supported:
            return ToolResult(tool="get_latest_market_metric", status="unavailable", metric=metric_name,
                              geography=geography, message=message).model_dump()
        region_ids = []
        if region_name is not None and geography is not None:
            resolved, missing, ambiguous = self.resolve_locations([region_name], geography)
            if ambiguous:
                return ToolResult(tool="get_latest_market_metric", status="unavailable", metric=metric_name,
                                  geography=geography, message=f"Ambiguous location '{region_name}': {ambiguous[region_name]}.").model_dump()
            if missing:
                return ToolResult(tool="get_latest_market_metric", status="unavailable", metric=metric_name,
                                  geography=geography, message=f"No {geography}-level location matches '{region_name}'.").model_dump()
            region_ids = [resolved[0]["region_id"]]
            frame = get_latest_observation_by_region_id(self.database, metric_name, region_ids[0], geography)
        else:
            frame = get_latest_observation(self.database, metric_name, region_name, geography)
        if frame.empty:
            return ToolResult(tool="get_latest_market_metric", status="unavailable", metric=metric_name,
                              geography=geography, message="No matching observation.").model_dump()
        return ToolResult(tool="get_latest_market_metric", status="ok", metric=metric_name,
                          unit=str(frame.unit.iloc[0]), geography=geography, region_ids=region_ids,
                          date_start=frame.date.min(), date_end=frame.date.max(), records=_records(frame)).model_dump()

    def langchain_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(self.available_metrics, name="list_available_metrics",
                description="List metrics, units, supported geography levels, and date coverage.", args_schema=NoArgs),
            StructuredTool.from_function(self.available_locations, name="list_available_locations",
                description="List exact supported New Jersey region names and geographic levels.", args_schema=LocationsArgs),
            StructuredTool.from_function(self.home_value_trend, name="get_home_value_trend",
                description="Get city-level Zillow Home Value Index history for one exact town name.", args_schema=TownArgs),
            StructuredTool.from_function(self.compare, name="compare_markets",
                description="Compare one supported metric across exact region names at one explicit geography.", args_schema=CompareArgs),
            StructuredTool.from_function(self.appreciation, name="calculate_appreciation",
                description="Calculate one- and five-year city ZHVI appreciation.", args_schema=TownArgs),
            StructuredTool.from_function(self.latest, name="get_latest_market_metric",
                description="Get the latest available supported metric without changing geography.", args_schema=LatestArgs),
        ]

