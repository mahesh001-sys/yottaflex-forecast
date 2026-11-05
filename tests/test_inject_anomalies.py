from pathlib import Path

import pandas as pd
import pytest

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


@pytest.fixture(scope="module")
def detected_anomaly_types(tmp_path_factory):
    from src.validate import run_checks

    anomaly_dir = tmp_path_factory.mktemp("detected_anomalies") / "anomalies"
    truth = create_anomaly_fixtures(
        raw_dir=RAW_DIR,
        anomaly_dir=anomaly_dir,
    )
    # Keep only the five labelled rows and the history needed to inspect them.
    # This keeps the focused detector test fast while exercising the same
    # validation entry point used by the full-data command.
    opportunity_ids = {
        item["record_id"] for item in truth
        if item["table"] == "opportunity"
    }
    snapshot_ids = {
        item["record_id"] for item in truth
        if item["table"] == "forecast_snapshot"
    }

    opportunities = pd.read_csv(anomaly_dir / "opportunity.csv")
    opportunities = opportunities[
        opportunities["opportunity_id"].isin(opportunity_ids)
    ]
    opportunities.to_csv(anomaly_dir / "opportunity.csv", index=False)

    snapshots = pd.read_csv(anomaly_dir / "forecast_snapshot.csv")
    labelled_snapshot_rows = snapshots[
        snapshots["forecast_snapshot_id"].isin(snapshot_ids)
    ]
    duplicate_keys = set(
        zip(labelled_snapshot_rows["snapshot_date"],
            labelled_snapshot_rows["opportunity_id"])
    )
    snapshots = snapshots[
        snapshots["forecast_snapshot_id"].isin(snapshot_ids)
        | snapshots.apply(
            lambda row: (row["snapshot_date"], row["opportunity_id"])
            in duplicate_keys,
            axis=1,
        )
    ]
    snapshots.to_csv(anomaly_dir / "forecast_snapshot.csv", index=False)

    related_opportunity_ids = set(snapshots["opportunity_id"])
    history = pd.read_csv(anomaly_dir / "stage_history.csv")
    history = history[history["opportunity_id"].isin(related_opportunity_ids)]
    history.to_csv(anomaly_dir / "stage_history.csv", index=False)

    issues, _ = run_checks(anomaly_dir)
    detected = {
        (issue["issue_type"], issue["record_id"])
        for issue in issues
    }
    expected = {
        (item["issue_type"], item["record_id"])
        for item in truth
    }
    return detected, expected


@pytest.mark.parametrize(
    "anomaly_type",
    [
        "close_date_before_creation",
        "mixed_currency",
        "stage_probability_mismatch",
        "future_information_leak",
        "duplicate_opportunity",
    ],
)
def test_each_injected_anomaly_is_detected(detected_anomaly_types, anomaly_type):
    detected, expected = detected_anomaly_types
    expected_ids = {record_id for issue_type, record_id in expected
                    if issue_type == anomaly_type}
    detected_ids = {record_id for issue_type, record_id in detected
                    if issue_type == anomaly_type}

    assert expected_ids, f"No ground-truth fixture for {anomaly_type}"
    assert expected_ids <= detected_ids, (
        f"{anomaly_type}: expected {expected_ids}, detected {detected_ids}"
    )
