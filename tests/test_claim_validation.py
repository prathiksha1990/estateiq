from real_estate.claim_validation import validate_numerical_claims


def analysis():
    return {"results": [
        {"metric": "for_sale_inventory", "unit": "homes", "geography": "msa", "records": [
            {"region_name": "Trenton, NJ", "geography": "msa", "date": "2026-09-30",
             "metric_name": "for_sale_inventory", "value": 100.0, "unit": "homes"}]},
        {"metric": "sales_count", "unit": "sales", "geography": "msa", "records": [
            {"region_name": "Atlantic City, NJ", "geography": "msa", "date": "2026-09-30",
             "metric_name": "sales_count", "value": 20.0, "unit": "sales"}]},
    ]}


def test_claim_binding_verifies_metric_location_date_unit_and_value():
    result = validate_numerical_claims(
        "Trenton, NJ MSA inventory was 100 homes on 2026-09-30. Atlantic City, NJ MSA sales count was 20 sales on 2026-09-30.",
        analysis())
    assert result.valid
    assert result.verified_claims == 2


def test_claim_binding_rejects_metric_confusion():
    result = validate_numerical_claims(
        "Trenton, NJ MSA sales count was 100 sales on 2026-09-30.", analysis())
    assert not result.valid
    assert "value/metric" in result.unverified_claims[0]["reasons"]


def test_claim_binding_rejects_location_confusion():
    result = validate_numerical_claims(
        "Atlantic City, NJ MSA inventory was 100 homes on 2026-09-30.", analysis())
    assert not result.valid
    assert "location" in result.unverified_claims[0]["reasons"]


def test_claim_binding_rejects_missing_as_zero():
    result = validate_numerical_claims("Trenton inventory was 0 homes.", analysis())
    assert not result.valid


def test_claim_binding_rejects_wrong_date():
    result = validate_numerical_claims(
        "Trenton, NJ MSA inventory was 100 homes on 2025-09-30.", analysis())
    assert not result.valid
    assert "date" in result.unverified_claims[0]["reasons"]


def test_claim_binding_rejects_wrong_direction():
    change = {"results": [{"metric": "for_sale_inventory", "unit": "homes", "geography": "msa",
        "calculations": [{"metric_name": "for_sale_inventory", "region_name": "Trenton, NJ",
            "geography": "msa", "unit": "homes", "latest_date": "2026-09-30",
            "1_year_pct": -10.0, "1_year_comparison_date": "2025-09-30"}]}]}
    result = validate_numerical_claims("Trenton, NJ inventory rose 10% over one year.", change)
    assert not result.valid
    assert "direction" in result.unverified_claims[0]["reasons"]
