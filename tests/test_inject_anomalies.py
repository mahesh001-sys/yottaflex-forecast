from pathlib import Path

import pandas as pd

from src.inject_anomalies import create_anomaly_fixtures


def test_anomaly_fixtures_are_created_and_source_is_unchanged(tmp_path):
    raw_dir = tmp_path / "raw"
    anomaly_dir = tmp_path / "anomalies"
    raw_dir.mkdir()

    source_path = raw_dir / "opportunity.csv"
    source = pd.DataFrame(
        [
            {
                "opportunity_id": "OPP-001",
                "currency_code": "USD",
                "created_date": "2025-01-15",
                "amount": 1000,
            },
            {
                "opportunity_id": "OPP-002",
                "currency_code": "USD",
                "created_date": "2025-02-15",
                "amount": 2000,
            },
        ]
    )
    source.to_csv(source_path, index=False)
    original_source_bytes = source_path.read_bytes()

    create_anomaly_fixtures(raw_dir=raw_dir, anomaly_dir=anomaly_dir)

    # Fixture generation must not modify the clean source file.
    assert source_path.read_bytes() == original_source_bytes

    duplicate = pd.read_csv(anomaly_dir / "duplicate_opportunity_id.csv")
    assert len(duplicate) == len(source) + 1
    assert duplicate["opportunity_id"].duplicated().any()

    invalid_currency = pd.read_csv(anomaly_dir / "invalid_currency.csv")
    assert invalid_currency.loc[0, "currency_code"] == "EUR"

    out_of_range_date = pd.read_csv(
        anomaly_dir / "out_of_range_created_date.csv"
    )
    assert out_of_range_date.loc[0, "created_date"] == "2027-01-01"

    ground_truth = pd.read_csv(anomaly_dir / "ground_truth.csv")
    assert len(ground_truth) == 3
    assert set(ground_truth["anomaly_type"]) == {
        "duplicate_primary_key",
        "invalid_currency",
        "out_of_range_date",
    }