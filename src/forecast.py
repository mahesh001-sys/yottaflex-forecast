"""Build opportunity-level weighted forecast detail and summary CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

SNAPSHOT_FILE = RAW_DIR / "forecast_snapshot.csv"
STAGE_FILE = RAW_DIR / "stage.csv"
OPPORTUNITY_FILE = RAW_DIR / "opportunity.csv"

DETAIL_FILE = PROCESSED_DIR / "forecast_detail.csv"
SUMMARY_FILE = PROCESSED_DIR / "forecast_summary.csv"


def calendar_quarter(values: pd.Series) -> pd.Series:
    """Convert dates to calendar-quarter labels such as 2026Q1."""
    dates = pd.to_datetime(values, errors="raise")
    return dates.dt.to_period("Q").astype(str)


def build_forecast(
    snapshot: pd.DataFrame,
    stages: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return opportunity-level detail and quarter/territory/stage summary.

    The snapshot's stage_id is the stage known at that snapshot's cutoff.
    Territory is joined from the opportunity record.
    """
    required_snapshot = {
        "forecast_snapshot_id",
        "snapshot_date",
        "opportunity_id",
        "stage_id",
        "amount",
    }
    required_stages = {"stage_id", "stage_name", "default_probability"}
    required_opportunities = {"opportunity_id", "territory_id"}

    for label, frame, required in (
        ("snapshot", snapshot, required_snapshot),
        ("stages", stages, required_stages),
        ("opportunities", opportunities, required_opportunities),
    ):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                f"{label} is missing required columns: {sorted(missing)}"
            )

    stage_lookup = stages[
        ["stage_id", "stage_name", "default_probability"]
    ].copy()
    stage_lookup["default_probability"] = pd.to_numeric(
        stage_lookup["default_probability"], errors="raise"
    )

    if stage_lookup["stage_id"].duplicated().any():
        raise ValueError("Stage table contains duplicate stage_id values.")

    if not stage_lookup["default_probability"].between(0, 1).all():
        raise ValueError("Stage probabilities must be between 0 and 1.")

    opportunity_lookup = opportunities[
        ["opportunity_id", "territory_id"]
    ].copy()

    if opportunity_lookup["opportunity_id"].duplicated().any():
        raise ValueError("Opportunity table contains duplicate opportunity_id values.")

    detail = snapshot.copy()
    detail["snapshot_date"] = pd.to_datetime(
        detail["snapshot_date"], errors="raise"
    )
    detail["amount"] = pd.to_numeric(detail["amount"], errors="raise")

    detail = detail.merge(
        stage_lookup,
        on="stage_id",
        how="left",
        validate="many_to_one",
        indicator="_stage_match",
    )
    missing_stages = detail.loc[
        detail["_stage_match"] != "both", "stage_id"
    ].drop_duplicates()
    if not missing_stages.empty:
        raise ValueError(
            f"Snapshot contains unknown stage_id values: "
            f"{missing_stages.tolist()}"
        )
    detail = detail.drop(columns="_stage_match")

    detail = detail.merge(
        opportunity_lookup,
        on="opportunity_id",
        how="left",
        validate="many_to_one",
        indicator="_opportunity_match",
    )
    missing_opportunities = detail.loc[
        detail["_opportunity_match"] != "both", "opportunity_id"
    ].drop_duplicates()
    if not missing_opportunities.empty:
        raise ValueError(
            f"Snapshot contains unknown opportunity_id values: "
            f"{missing_opportunities.tolist()}"
        )
    detail = detail.drop(columns="_opportunity_match")

    detail["quarter"] = calendar_quarter(detail["snapshot_date"])
    detail["stage_probability"] = detail["default_probability"]
    detail["expected_revenue"] = (
        detail["amount"] * detail["stage_probability"]
    ).round(2)

    detail = detail[
        [
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
        ]
    ].sort_values(
        ["snapshot_date", "territory_id", "stage_id", "opportunity_id"],
        kind="stable",
    ).reset_index(drop=True)

    summary = (
        detail.groupby(
            ["quarter", "territory_id", "stage_id", "stage_name"],
            as_index=False,
            dropna=False,
        )
        .agg(
            opportunity_count=("opportunity_id", "size"),
            total_amount=("amount", "sum"),
            total_weighted_pipeline=("expected_revenue", "sum"),
        )
        .sort_values(
            ["quarter", "territory_id", "stage_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    summary["total_amount"] = summary["total_amount"].round(2)
    summary["total_weighted_pipeline"] = summary[
        "total_weighted_pipeline"
    ].round(2)

    detail_total = round(float(detail["expected_revenue"].sum()), 2)
    summary_total = round(float(summary["total_weighted_pipeline"].sum()), 2)
    if detail_total != summary_total:
        raise AssertionError(
            "Forecast summary does not reconcile to forecast detail: "
            f"{summary_total} != {detail_total}"
        )

    return detail, summary


def run(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> tuple[Path, Path]:
    """Load raw CSVs, build the forecast, and write processed CSVs."""
    snapshot = pd.read_csv(raw_dir / "forecast_snapshot.csv")
    stages = pd.read_csv(raw_dir / "stage.csv")
    opportunities = pd.read_csv(raw_dir / "opportunity.csv")

    detail, summary = build_forecast(snapshot, stages, opportunities)

    processed_dir.mkdir(parents=True, exist_ok=True)
    detail_path = processed_dir / "forecast_detail.csv"
    summary_path = processed_dir / "forecast_summary.csv"

    detail.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"Wrote {len(detail):,} detail rows to {detail_path}")
    print(f"Wrote {len(summary):,} summary rows to {summary_path}")
    print(
        "Total weighted pipeline: "
        f"${detail['expected_revenue'].sum():,.2f}"
    )

    return detail_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build weighted forecast detail and summary CSV files."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_DIR,
        help="Directory containing the raw CSV files.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=PROCESSED_DIR,
        help="Directory where forecast CSV files will be written.",
    )
    args = parser.parse_args()
    run(args.raw_dir, args.processed_dir)


if __name__ == "__main__":
    main()