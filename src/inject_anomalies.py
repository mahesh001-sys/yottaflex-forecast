"""Create isolated, deterministic anomaly fixtures for evaluation.

Run from the repository root:
    python -m src.inject_anomalies

The clean source tables in data/raw are read-only inputs. All injected
fixtures and their ground-truth index are written under data/anomalies.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


RAW_DIR = Path("data/raw")
ANOMALY_DIR = Path("data/anomalies")

GROUND_TRUTH_COLUMNS = [
    "anomaly_id",
    "fixture_file",
    "table_name",
    "record_key",
    "anomaly_type",
    "field_name",
    "expected_value",
    "injected_value",
]


def _load_opportunities() -> pd.DataFrame:
    path = RAW_DIR / "opportunity.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Generate the clean dataset first."
        )

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {
        "opportunity_id",
        "created_date",
        "currency_code",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {sorted(missing)}"
        )
    if frame.empty:
        raise ValueError(f"{path} has no rows to use as a fixture.")

    return frame


def create_anomaly_fixtures(
    raw_dir: Path = RAW_DIR,
    anomaly_dir: Path = ANOMALY_DIR,
) -> pd.DataFrame:
    """Create three isolated anomaly fixtures and return their ground truth."""
    source_path = raw_dir / "opportunity.csv"
    if not source_path.exists():
        raise FileNotFoundError(
            f"Missing {source_path}. Generate the clean dataset first."
        )

    opportunities = pd.read_csv(
        source_path,
        dtype=str,
        keep_default_na=False,
    )

    required = {
        "opportunity_id",
        "created_date",
        "currency_code",
    }
    missing = required.difference(opportunities.columns)
    if missing:
        raise ValueError(
            f"{source_path} is missing required columns: {sorted(missing)}"
        )
    if opportunities.empty:
        raise ValueError(f"{source_path} has no rows to use as a fixture.")

    anomaly_dir.mkdir(parents=True, exist_ok=True)

    # Case 1: duplicate primary key. Keep the original row and append a copy.
    duplicate_fixture = opportunities.copy()
    source_row = opportunities.iloc[0].copy()
    duplicate_fixture = pd.concat(
        [duplicate_fixture, source_row.to_frame().T],
        ignore_index=True,
    )
    duplicate_fixture.to_csv(
        anomaly_dir / "duplicate_opportunity_id.csv",
        index=False,
    )

    # Case 2: invalid currency. The project assumption requires USD.
    currency_fixture = opportunities.copy()
    currency_fixture.loc[0, "currency_code"] = "EUR"
    currency_fixture.to_csv(
        anomaly_dir / "invalid_currency.csv",
        index=False,
    )

    # Case 3: out-of-range date. The documented data horizon ends 2026-12-31.
    date_fixture = opportunities.copy()
    date_fixture.loc[0, "created_date"] = "2027-01-01"
    date_fixture.to_csv(
        anomaly_dir / "out_of_range_created_date.csv",
        index=False,
    )

    original_id = str(source_row["opportunity_id"])
    original_currency = str(source_row["currency_code"])
    original_date = str(source_row["created_date"])

    ground_truth = pd.DataFrame(
        [
            {
                "anomaly_id": "ANOM-001",
                "fixture_file": "duplicate_opportunity_id.csv",
                "table_name": "opportunity",
                "record_key": original_id,
                "anomaly_type": "duplicate_primary_key",
                "field_name": "opportunity_id",
                "expected_value": original_id,
                "injected_value": original_id,
            },
            {
                "anomaly_id": "ANOM-002",
                "fixture_file": "invalid_currency.csv",
                "table_name": "opportunity",
                "record_key": original_id,
                "anomaly_type": "invalid_currency",
                "field_name": "currency_code",
                "expected_value": "USD",
                "injected_value": "EUR",
            },
            {
                "anomaly_id": "ANOM-003",
                "fixture_file": "out_of_range_created_date.csv",
                "table_name": "opportunity",
                "record_key": original_id,
                "anomaly_type": "out_of_range_date",
                "field_name": "created_date",
                "expected_value": original_date,
                "injected_value": "2027-01-01",
            },
        ],
        columns=GROUND_TRUTH_COLUMNS,
    )

    ground_truth.to_csv(
        anomaly_dir / "ground_truth.csv",
        index=False,
    )
    return ground_truth


def main() -> None:
    ground_truth = create_anomaly_fixtures()
    print(f"Created {len(ground_truth)} anomaly fixtures in {ANOMALY_DIR}:")
    for row in ground_truth.itertuples(index=False):
        print(f"  {row.anomaly_id}: {row.anomaly_type} -> {row.fixture_file}")
    print("Clean files in data/raw were not modified.")


if __name__ == "__main__":
    main()