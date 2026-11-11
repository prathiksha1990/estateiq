import re
from dataclasses import dataclass, field
from typing import Any


METRIC_ALIASES = {
    "zhvi": ("zhvi", "home value", "typical home value", "zillow home value index"),
    "zhvi_appreciation": ("appreciation", "appreciated", "growth", "grew", "rose", "fell", "increased", "decreased"),
    "median_sale_price": ("median sale price", "sale price"),
    "for_sale_inventory": ("inventory", "homes for sale", "for-sale"),
    "sales_count": ("sales count", "monthly sales", "sales"),
    "median_days_to_pending": ("days to pending", "pending"),
    "market_heat_index": ("market heat", "heat index"),
}


@dataclass
class EvidencePoint:
    value: float
    metric: str
    unit: str
    geography: str | None
    region_name: str | None
    date_start: str | None
    date_end: str | None
    label: str


@dataclass
class ClaimValidation:
    valid: bool
    verified_claims: int = 0
    unverified_claims: list[dict[str, Any]] = field(default_factory=list)


def _point(value, metric, unit, geography, region, start, end, label):
    if value is None:
        return None
    return EvidencePoint(float(value), metric, unit, geography, region, start, end, label)


def evidence_points(analysis: dict) -> list[EvidencePoint]:
    points = []
    for result in analysis.get("results", []):
        metric = result.get("metric") or ""
        geography, unit = result.get("geography"), result.get("unit") or ""
        for record in result.get("records", []):
            if record.get("value") is not None:
                points.append(_point(record["value"], record.get("metric_name") or metric, record.get("unit") or unit,
                                     record.get("geography") or geography, record.get("region_name"),
                                     record.get("date"), record.get("date"), "observation"))
            if record.get("latest_value") is not None:
                points.append(_point(record["latest_value"], "zhvi", "USD", geography, record.get("region_name"),
                                     record.get("as_of_date"), record.get("as_of_date"), "latest_value"))
            for years, key in ((1, "one_year_pct"), (5, "five_year_pct")):
                if record.get(key) is not None:
                    points.append(_point(record[key], "zhvi_appreciation", "percent", geography,
                        record.get("region_name"), record.get(key.replace("pct", "comparison_date")),
                        record.get("as_of_date"), f"{years}_year_appreciation"))
        for calculation in result.get("calculations", []):
            region = calculation.get("region_name")
            calc_metric = calculation.get("metric_name") or metric
            calc_unit = calculation.get("unit") or unit
            if calculation.get("latest_value") is not None:
                points.append(_point(calculation["latest_value"], calc_metric, calc_unit, geography, region,
                                     calculation.get("latest_date"), calculation.get("latest_date"), "latest_value"))
            for years in (1, 5):
                key = f"{years}_year_pct"
                if calculation.get(key) is not None:
                    points.append(_point(calculation[key], calc_metric, "percent", geography, region,
                        calculation.get(f"{years}_year_comparison_date"), calculation.get("latest_date"),
                        f"{years}_year_change"))
            if calculation.get("left_minus_right") is not None:
                points.append(_point(calculation["left_minus_right"], calc_metric, calc_unit, geography, None,
                                     result.get("date_end"), result.get("date_end"), "latest_value_difference"))
    return [point for point in points if point is not None]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", text) if part.strip()]


def _direction(sentence: str) -> int | None:
    matches = [(match.start(), -1) for match in
               re.finditer(r"\b(fell|decreased|declined|down|dropped)\b", sentence, re.I)]
    matches.extend((match.start(), 1) for match in
                   re.finditer(r"\b(rose|increased|grew|up|gained)\b", sentence, re.I))
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def _metric_matches(sentence: str, point: EvidencePoint, all_metrics: set[str]) -> bool:
    lowered = sentence.casefold()
    aliases = METRIC_ALIASES.get(point.metric, (point.metric.replace("_", " "),))
    if any(alias in lowered for alias in aliases):
        return True
    if point.unit == "percent" and any(word in lowered for word in METRIC_ALIASES["zhvi_appreciation"]):
        return True
    return len(all_metrics) == 1


def _unit_matches(sentence: str, point: EvidencePoint) -> bool:
    lowered = sentence.casefold()
    unit = point.unit.casefold()
    if unit == "usd": return "$" in sentence or "usd" in lowered or "price" in lowered or "value" in lowered
    if unit == "percent": return "%" in sentence or "percent" in lowered
    if unit == "homes": return "home" in lowered or "inventory" in lowered
    if unit == "sales": return "sale" in lowered
    if unit == "days": return "day" in lowered
    if unit == "index": return "index" in lowered
    return unit in lowered if unit else True


def validate_numerical_claims(text: str, analysis: dict) -> ClaimValidation:
    points = evidence_points(analysis)
    all_metrics = {point.metric for point in points}
    all_regions = {point.region_name for point in points if point.region_name}
    verified, unverified = 0, []
    for sentence in _sentences(text):
        normalized = sentence.replace("‑", "-").replace("–", "-")
        date_claims = re.findall(r"\d{4}-\d{2}-\d{2}", normalized)
        without_dates = re.sub(r"\d{4}-\d{2}-\d{2}", "", normalized)
        without_periods = re.sub(r"\b(?:1|5)[- ]year\b", "", without_dates, flags=re.I)
        claim_matches = list(re.finditer(r"(?<![\w])[-+]?\$?(\d[\d,]*(?:\.\d+)?)", without_periods))
        for match in claim_matches:
            claim = float(match.group(1).replace(",", ""))
            if claim in (1.0, 5.0) and re.search(r"year|anniversary", sentence, re.I):
                continue
            candidates = [point for point in points if
                          abs(abs(claim) - abs(point.value)) <= max(0.02, abs(point.value) * 0.00001) or
                          claim == round(point.value) or claim == round(point.value, 2)]
            reasons = []
            candidates = [point for point in candidates if _metric_matches(sentence, point, all_metrics)]
            if not candidates: reasons.append("value/metric")
            unit_candidates = [point for point in candidates if _unit_matches(sentence, point)]
            if candidates and not unit_candidates: reasons.append("unit")
            candidates = unit_candidates
            if len(all_regions) > 1:
                region_candidates = [point for point in candidates if not point.region_name or
                                     point.region_name.split(",")[0].casefold() in sentence.casefold()]
                if candidates and not region_candidates: reasons.append("location")
                candidates = region_candidates
            if date_claims:
                date_candidates = [point for point in candidates if
                                   point.date_start in date_claims or point.date_end in date_claims]
                if candidates and not date_candidates: reasons.append("date")
                candidates = date_candidates
            direction = _direction(without_periods[max(0, match.start() - 48):match.start()])
            if direction is not None:
                directed = [point for point in candidates if point.value == 0 or
                            (point.value > 0 and direction > 0) or (point.value < 0 and direction < 0)]
                if candidates and not directed: reasons.append("direction")
                candidates = directed
            if candidates:
                verified += 1
            else:
                unverified.append({"claim": claim, "sentence": sentence, "reasons": reasons or ["unsupported"]})
    return ClaimValidation(valid=not unverified, verified_claims=verified, unverified_claims=unverified)
