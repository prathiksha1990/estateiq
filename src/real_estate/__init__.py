"""New Jersey real-estate data ingestion and query tools."""

from .queries import (calculate_home_value_appreciation, compare_towns,
                      get_historical_home_values, get_latest_observation,
                      list_locations, list_metrics)

__all__ = [
    "calculate_home_value_appreciation", "compare_towns",
    "get_historical_home_values", "get_latest_observation",
    "list_locations", "list_metrics",
]

