from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    metric_name: str
    unit: str
    description: str
    nonnegative: bool = True


DATASETS = {
    "zhvi_home_values.csv": DatasetSpec("zhvi", "USD", "Zillow Home Value Index"),
    "for_sale_inventory.csv": DatasetSpec("for_sale_inventory", "homes", "For-sale inventory"),
    "median_sale_price.csv": DatasetSpec("median_sale_price", "USD", "Median sale price"),
    "median_sale_price_monthly.csv": DatasetSpec("median_sale_price", "USD", "Median sale price"),
    "sales_count.csv": DatasetSpec("sales_count", "sales", "Sales count"),
    "sales_count_monthly.csv": DatasetSpec("sales_count", "sales", "Sales count"),
    "median_days_to_pending.csv": DatasetSpec("median_days_to_pending", "days", "Median days to pending"),
    "median_days_to_pending_monthly.csv": DatasetSpec("median_days_to_pending", "days", "Median days to pending"),
    "market_heat_index.csv": DatasetSpec("market_heat_index", "index", "Zillow market heat index"),
    "market_temp_index_month.csv": DatasetSpec("market_heat_index", "index", "Zillow market heat index"),
}

OPTIONAL_METRICS = tuple(sorted({s.metric_name for s in DATASETS.values()}))

