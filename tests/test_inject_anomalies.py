from pathlib import Path

import pandas as pd

from src.inject_anomalies import RAW_DIR, create_anomaly_fixtures


def test_anomaly_fixtures_are_created_and_source_is_unchanged(tmp_path):
    anomaly_dir = tmp_path / "anomalies"

    source_files = [
        "opportunity.csv",
        "forecast_snapshot.csv",
        "stage.csv",
        "stage_history.csv",
    ]

    original_files = {
        filename: (RAW_DIR / filename).read_bytes()
        for filename in source_files
    }

    truth = create_anomaly_fixtures(
        raw_dir=RAW_DIR,
        anomaly_dir=anomaly_dir,
    )

    # The clean source data must remain unchanged.
    for filename, original_bytes in original_files.items():
        assert (RAW_DIR / filename).read_bytes() == original_bytes

    # Exactly five labelled anomalies must be created.
    assert len(truth) == 5

    expected_types = {
        "close_date_before_creation",
        "mixed_currency",
        "stage_probability_mismatch",
        "future_information_leak",
        "duplicate_opportunity",
    }

    assert {item["issue_type"] for item in truth} == expected_types

    # Ground-truth CSV and JSON must both be generated.
    ground_truth_csv = pd.read_csv(anomaly_dir / "ground_truth.csv")
    ground_truth_json = pd.read_json(anomaly_dir / "ground_truth.json")

    assert len(ground_truth_csv) == 5
    assert len(ground_truth_json) == 5

    # The opportunity anomalies must be present in the copied dataset.
    opportunities = pd.read_csv(anomaly_dir / "opportunity.csv")

    close_anomaly = next(
        item for item in truth
        if item["issue_type"] == "close_date_before_creation"
    )

    close_row = opportunities.loc[
        opportunities["opportunity_id"] == close_anomaly["record_id"]
    ].iloc[0]

    assert pd.to_datetime(close_row["closed_date"]) < pd.to_datetime(
        close_row["created_date"]
    )

    currency_anomaly = next(
        item for item in truth
        if item["issue_type"] == "mixed_currency"
    )

    currency_row = opportunities.loc[
        opportunities["opportunity_id"] == currency_anomaly["record_id"]
    ].iloc[0]

    assert currency_row["currency_code"] == "EUR"

    # The snapshot dataset must contain the injected anomalies.
    snapshots = pd.read_csv(anomaly_dir / "forecast_snapshot.csv")

    duplicate_anomaly = next(
        item for item in truth
        if item["issue_type"] == "duplicate_opportunity"
    )

    assert duplicate_anomaly["record_id"] in set(
        snapshots["forecast_snapshot_id"]
    )

    assert len(snapshots) == len(
        pd.read_csv(RAW_DIR / "forecast_snapshot.csv")
    ) + 1

    assert (
        "stage_probability"
        in snapshots.columns
    )