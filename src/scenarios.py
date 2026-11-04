"""Build baseline, pessimistic, and optimistic forecast scenarios."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROCESSED_DIR = Path("data/processed")
FORECAST_DETAIL_FILE = PROCESSED_DIR / "forecast_detail.csv"

SCENARIO_DETAIL_FILE = PROCESSED_DIR / "scenario_detail.csv"
SCENARIO_SUMMARY_FILE = PROCESSED_DIR / "scenario_summary.csv"

SCENARIO_FACTORS = {
    "Baseline": {
        "probability_factor": 1.00,
        "revenue_factor": 1.00,
    },
    "Pessimistic": {
        "probability_factor": 0.75,
        "revenue_factor": 0.85,
    },
    "Optimistic": {
        "probability_factor": 1.20,
        "revenue_factor": 1.00,
    },
}


def build_scenarios(
    forecast_detail: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return scenario detail (3x input rows) and grouped scenario summary."""
    required = {
        "forecast_snapshot_id",
        "snapshot_date",
        "quarter",
        "opportunity_id",
        "territory_id",
        "stage_id",
        "stage_name",
        "amount",
        "stage_probability",
        "expected_revenue",
    }
    missing = required - set(forecast_detail.columns)
    if missing:
        raise ValueError(
            f"Forecast detail is missing required columns: {sorted(missing)}"
        )

    base = forecast_detail.copy()
    base["amount"] = pd.to_numeric(base["amount"], errors="raise")
    base["stage_probability"] = pd.to_numeric(
        base["stage_probability"], errors="raise"
    )

    if not base["stage_probability"].between(0, 1).all():
        raise ValueError("Baseline probabilities must be between 0 and 1.")

    scenario_frames = []

    for scenario, factors in SCENARIO_FACTORS.items():
        scenario_rows = base.copy()
        scenario_rows["scenario"] = scenario
        scenario_rows["probability_factor"] = factors["probability_factor"]
        scenario_rows["revenue_factor"] = factors["revenue_factor"]

        scenario_rows["scenario_probability"] = (
            scenario_rows["stage_probability"]
            * scenario_rows["probability_factor"]
        ).clip(lower=0, upper=1)

        scenario_rows["scenario_expected_revenue"] = (
            scenario_rows["amount"]
            * scenario_rows["scenario_probability"]
            * scenario_rows["revenue_factor"]
        ).round(2)

        scenario_frames.append(scenario_rows)

    detail = pd.concat(scenario_frames, ignore_index=True)

    detail = detail[
        [
            "scenario",
            "forecast_snapshot_id",
            "snapshot_date",
            "quarter",
            "opportunity_id",
            "territory_id",
            "stage_id",
            "stage_name",
            "amount",
            "stage_probability",
            "probability_factor",
            "scenario_probability",
            "revenue_factor",
            "scenario_expected_revenue",
        ]
    ].sort_values(
        [
            "scenario",
            "snapshot_date",
            "territory_id",
            "stage_id",
            "opportunity_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    summary = (
        detail.groupby(
            ["scenario", "quarter", "territory_id", "stage_id", "stage_name"],
            as_index=False,
            dropna=False,
        )
        .agg(
            opportunity_count=("opportunity_id", "size"),
            total_amount=("amount", "sum"),
            total_weighted_pipeline=("scenario_expected_revenue", "sum"),
        )
        .sort_values(
            ["scenario", "quarter", "territory_id", "stage_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    summary["total_amount"] = summary["total_amount"].round(2)
    summary["total_weighted_pipeline"] = summary[
        "total_weighted_pipeline"
    ].round(2)

    detail_totals = detail.groupby("scenario")[
        "scenario_expected_revenue"
    ].sum()
    summary_totals = summary.groupby("scenario")[
        "total_weighted_pipeline"
    ].sum()

    for scenario in SCENARIO_FACTORS:
        detail_total = round(float(detail_totals.loc[scenario]), 2)
        summary_total = round(float(summary_totals.loc[scenario]), 2)
        if detail_total != summary_total:
            raise AssertionError(
                f"{scenario} summary does not reconcile to detail: "
                f"{summary_total} != {detail_total}"
            )

    return detail, summary


def run(
    processed_dir: Path = PROCESSED_DIR,
) -> tuple[Path, Path]:
    """Load forecast detail, build scenarios, and write output CSVs."""
    forecast_detail = pd.read_csv(processed_dir / "forecast_detail.csv")
    detail, summary = build_scenarios(forecast_detail)

    processed_dir.mkdir(parents=True, exist_ok=True)
    detail_path = processed_dir / "scenario_detail.csv"
    summary_path = processed_dir / "scenario_summary.csv"

    detail.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"Wrote {len(detail):,} scenario detail rows to {detail_path}")
    print(f"Wrote {len(summary):,} scenario summary rows to {summary_path}")

    for scenario, total in detail.groupby("scenario")[
        "scenario_expected_revenue"
    ].sum().items():
        print(f"{scenario} weighted pipeline: ${total:,.2f}")

    return detail_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build forecast scenario detail and summary CSV files."
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=PROCESSED_DIR,
        help="Directory containing forecast detail and receiving scenario outputs.",
    )
    args = parser.parse_args()
    run(args.processed_dir)


if __name__ == "__main__":
    main()