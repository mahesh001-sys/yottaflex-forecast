"""Build baseline and adjusted sales forecasts."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

ACTIVITY_LOOKBACK_DAYS = 30
NO_ACTIVITY_FACTOR = 0.80
HIGH_ACTIVITY_FACTOR = 1.10
OLD_DEAL_FACTOR = 0.80

DEFAULT_STAGE_PROBABILITIES = {
    "Discovery": 0.10,
    "Qualification": 0.20,
    "Proposal": 0.40,
    "Negotiation": 0.60,
    "Closed Won": 1.00,
    "Closed Lost": 0.00,
}


def _first_existing_column(
    frame: pd.DataFrame, names: list[str]
) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _parse_utc_as_naive(series: pd.Series) -> pd.Series:
    """Parse timestamps as UTC and remove timezone for consistent comparisons."""
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None)


def _normalise_stage(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().casefold()


def _prepare_history(stage_history: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "opportunity_id",
        "from_stage_id",
        "to_stage_id",
        "changed_at",
    ]
    if stage_history is None or stage_history.empty:
        return pd.DataFrame(columns=columns)

    history = stage_history.copy()
    required = {"opportunity_id", "changed_at"}
    missing = required - set(history.columns)
    if missing:
        raise ValueError(
            f"stage_history is missing required columns: {sorted(missing)}"
        )

    for column in ("from_stage_id", "to_stage_id"):
        if column not in history.columns:
            history[column] = pd.NA

    history["changed_at"] = _parse_utc_as_naive(history["changed_at"])
    history = history.dropna(subset=["opportunity_id", "changed_at"])
    return history.sort_values(
        ["opportunity_id", "changed_at"], kind="stable"
    ).reset_index(drop=True)


def _prepare_activity(activity: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["opportunity_id", "activity_date", "outcome"]
    if activity is None or activity.empty:
        return pd.DataFrame(columns=columns)

    prepared = activity.copy()
    if "opportunity_id" not in prepared.columns:
        raise ValueError("activity is missing required column: opportunity_id")

    date_column = _first_existing_column(
        prepared, ["activity_date", "activity_at", "created_at", "date"]
    )
    if date_column is None:
        raise ValueError(
            "activity must contain one of: activity_date, activity_at, "
            "created_at, date"
        )

    prepared["activity_date"] = _parse_utc_as_naive(prepared[date_column])

    if "outcome" not in prepared.columns:
        if "status" in prepared.columns:
            prepared["outcome"] = prepared["status"]
        else:
            prepared["outcome"] = "Completed"

    prepared = prepared.dropna(subset=["opportunity_id", "activity_date"])
    return prepared.reset_index(drop=True)


def _prepare_stages(stages: pd.DataFrame) -> pd.DataFrame:
    prepared = stages.copy()
    if "stage_id" not in prepared.columns:
        raise ValueError("stages is missing required column: stage_id")

    name_column = _first_existing_column(
        prepared, ["stage_name", "name", "label"]
    )
    if name_column is None:
        raise ValueError("stages must contain stage_name, name, or label")
    prepared["stage_name"] = prepared[name_column].astype(str)

    probability_column = _first_existing_column(
        prepared, ["default_probability", "probability", "win_probability"]
    )
    if probability_column is None:
        prepared["default_probability"] = prepared["stage_name"].map(
            DEFAULT_STAGE_PROBABILITIES
        )
    else:
        prepared["default_probability"] = pd.to_numeric(
            prepared[probability_column], errors="coerce"
        )

    prepared["default_probability"] = (
        prepared["default_probability"].fillna(0.0).clip(0.0, 1.0)
    )
    return prepared


def _prepare_opportunities(opportunities: pd.DataFrame) -> pd.DataFrame:
    prepared = opportunities.copy()
    if "opportunity_id" not in prepared.columns:
        raise ValueError("opportunities is missing required column: opportunity_id")

    if "closed_date" in prepared.columns:
        prepared["closed_date"] = _parse_utc_as_naive(prepared["closed_date"])
    else:
        prepared["closed_date"] = pd.NaT

    if "outcome" not in prepared.columns:
        prepared["outcome"] = pd.NA

    if "territory_id" not in prepared.columns:
        prepared["territory_id"] = pd.NA

    return prepared


def _prepare_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    prepared = snapshot.copy()
    required = {"opportunity_id", "stage_id", "amount"}
    missing = required - set(prepared.columns)
    if missing:
        raise ValueError(
            f"snapshot is missing required columns: {sorted(missing)}"
        )

    if "snapshot_date" not in prepared.columns:
        raise ValueError("snapshot is missing required column: snapshot_date")

    prepared["snapshot_date"] = _parse_utc_as_naive(
        prepared["snapshot_date"]
    )
    if prepared["snapshot_date"].isna().any():
        raise ValueError("snapshot contains an invalid snapshot_date")

    if "forecast_snapshot_id" not in prepared.columns:
        prepared["forecast_snapshot_id"] = pd.NA

    prepared["amount"] = pd.to_numeric(
        prepared["amount"], errors="coerce"
    ).fillna(0.0)

    prepared["quarter"] = (
        prepared["snapshot_date"].dt.to_period("Q").astype(str)
    )
    return prepared


def _historical_stage_rates(
    snapshot_date: pd.Timestamp,
    opportunities: pd.DataFrame,
    stages: pd.DataFrame,
    history: pd.DataFrame,
) -> dict:
    """Calculate stage win rates from opportunities closed before the snapshot."""
    if opportunities.empty or history.empty:
        return {}

    closed = opportunities[
        opportunities["closed_date"].notna()
        & (opportunities["closed_date"] < snapshot_date)
    ].copy()
    if closed.empty:
        return {}

    outcomes = closed["outcome"].astype(str).str.strip().str.upper()
    closed = closed[outcomes.isin({"WON", "LOST", "CLOSED WON", "CLOSED LOST"})]
    if closed.empty:
        return {}

    closed_ids = set(closed["opportunity_id"])
    eligible = history[
        history["opportunity_id"].isin(closed_ids)
        & (history["changed_at"] <= snapshot_date)
    ].copy()
    if eligible.empty:
        return {}

    eligible["stage_id"] = eligible["to_stage_id"].where(
        eligible["to_stage_id"].notna(), eligible["from_stage_id"]
    )
    eligible = eligible.dropna(subset=["stage_id"])
    reached = eligible[["opportunity_id", "stage_id"]].drop_duplicates()
    if reached.empty:
        return {}

    outcome_by_id = (
        closed.assign(
            _won=closed["outcome"]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin({"WON", "CLOSED WON"})
        )
        .set_index("opportunity_id")["_won"]
        .to_dict()
    )
    reached["_won"] = reached["opportunity_id"].map(outcome_by_id)

    rates = {}
    for stage_id, group in reached.groupby("stage_id"):
        rate = float(group["_won"].mean())
        rates[stage_id] = rate

    stage_names = stages.set_index("stage_id")["stage_name"].to_dict()
    for stage_id, rate in list(rates.items()):
        stage_name = stage_names.get(stage_id)
        if stage_name is not None:
            rates[_normalise_stage(stage_name)] = rate

    return rates


def _stage_ages(
    snapshot_date: pd.Timestamp,
    history: pd.DataFrame,
) -> pd.Series:
    """Return days since each opportunity's latest stage-history event."""
    if history.empty:
        return pd.Series(dtype=float)

    eligible = history[history["changed_at"] <= snapshot_date]
    if eligible.empty:
        return pd.Series(dtype=float)

    latest = (
        eligible.sort_values("changed_at", kind="stable")
        .drop_duplicates("opportunity_id", keep="last")
        .set_index("opportunity_id")["changed_at"]
    )
    return (
        (snapshot_date - latest).dt.total_seconds() / 86400
    ).clip(lower=0)


def _activity_counts(
    snapshot_date: pd.Timestamp,
    activity: pd.DataFrame,
) -> pd.Series:
    """Count completed activities in the 30 days before the snapshot."""
    if activity.empty:
        return pd.Series(dtype=int)

    start_date = snapshot_date - pd.Timedelta(days=ACTIVITY_LOOKBACK_DAYS)
    eligible = activity[
        (activity["activity_date"] >= start_date)
        & (activity["activity_date"] < snapshot_date)
    ].copy()

    completed = (
        eligible["outcome"].astype(str).str.strip().str.upper().isin(
            {"COMPLETED", "DONE", "FINISHED"}
        )
    )
    eligible = eligible[completed]
    return eligible.groupby("opportunity_id").size()


def build_forecast(
    snapshot: pd.DataFrame,
    stages: pd.DataFrame,
    opportunities: pd.DataFrame,
    stage_history: pd.DataFrame | None = None,
    activity: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return forecast detail and summary, preserving baseline calculations."""
    prepared_snapshot = _prepare_snapshot(snapshot)
    prepared_stages = _prepare_stages(stages)
    prepared_opportunities = _prepare_opportunities(opportunities)
    history = _prepare_history(stage_history)
    prepared_activity = _prepare_activity(activity)

    # The snapshot is the source of stage, amount, and forecast date.
    forecast = prepared_snapshot.merge(
        prepared_opportunities,
        on="opportunity_id",
        how="left",
        suffixes=("", "_opportunity"),
        validate="many_to_one",
    )

    stage_columns = prepared_stages[
        ["stage_id", "stage_name", "default_probability"]
    ].drop_duplicates("stage_id")
    forecast = forecast.merge(
        stage_columns,
        on="stage_id",
        how="left",
        validate="many_to_one",
    )

    forecast["stage_name"] = forecast["stage_name"].fillna(
        forecast["stage_id"].astype(str)
    )

    forecast["stage_probability"] = (
        forecast["default_probability"].fillna(0.0).clip(0.0, 1.0)
    )
    # Keep the baseline probability under the column name used by evaluate.py.
    forecast["baseline_probability"] = forecast["stage_probability"]

    forecast["expected_revenue"] = (
        forecast["amount"] * forecast["baseline_probability"]
    )

    # Calculate historical rates using each snapshot's own cutoff.
    historical_rates_by_date = {}
    for snapshot_date in forecast["snapshot_date"].drop_duplicates():
        historical_rates_by_date[snapshot_date] = _historical_stage_rates(
            snapshot_date,
            prepared_opportunities,
            prepared_stages,
            history,
        )

    forecast["historical_stage_win_rate"] = forecast.apply(
        lambda row: historical_rates_by_date[row["snapshot_date"]].get(
            row["stage_id"],
            historical_rates_by_date[row["snapshot_date"]].get(
                _normalise_stage(row["stage_name"]),
                row["stage_probability"],
            ),
        ),
        axis=1,
    )

    # Compute stage age and activity count as of each row's snapshot date.
    age_values = {}
    activity_values = {}
    for snapshot_date in forecast["snapshot_date"].drop_duplicates():
        age_values[snapshot_date] = _stage_ages(snapshot_date, history)
        activity_values[snapshot_date] = _activity_counts(
            snapshot_date, prepared_activity
        )

    forecast["stage_age_days"] = forecast.apply(
        lambda row: age_values[row["snapshot_date"]].get(
            row["opportunity_id"], float("nan")
        ),
        axis=1,
    )
    forecast["activity_count_30d"] = forecast.apply(
        lambda row: int(
            activity_values[row["snapshot_date"]].get(
                row["opportunity_id"], 0
            )
        ),
        axis=1,
    )
    # Keep the earlier column name too for compatibility with existing outputs.
    forecast["recent_activity_count"] = forecast["activity_count_30d"]

    stage_medians = forecast.groupby("stage_id")["stage_age_days"].transform(
        "median"
    )
    forecast["age_factor"] = 1.0
    old_deal = (
        forecast["stage_age_days"].notna()
        & stage_medians.notna()
        & (forecast["stage_age_days"] > stage_medians)
    )
    forecast.loc[old_deal, "age_factor"] = OLD_DEAL_FACTOR

    forecast["activity_factor"] = 1.0
    forecast.loc[
        forecast["activity_count_30d"] == 0, "activity_factor"
    ] = NO_ACTIVITY_FACTOR
    forecast.loc[
        forecast["activity_count_30d"] >= 3, "activity_factor"
    ] = HIGH_ACTIVITY_FACTOR

    forecast["adjusted_is_stale"] = forecast["activity_count_30d"] == 0
    forecast["stale_activity"] = forecast["adjusted_is_stale"]

    forecast["adjusted_probability"] = (
        forecast["historical_stage_win_rate"]
        * forecast["age_factor"]
        * forecast["activity_factor"]
    ).clip(0.0, 1.0)
    forecast["adjusted_expected_revenue"] = (
        forecast["amount"] * forecast["adjusted_probability"]
    )

    summary = (
        forecast.groupby(
            ["quarter", "territory_id", "stage_id", "stage_name"],
            as_index=False,
            dropna=False,
        )
        .agg(
            opportunity_count=("opportunity_id", "size"),
            total_amount=("amount", "sum"),
            total_weighted_pipeline=("expected_revenue", "sum"),
            adjusted_expected_revenue=("adjusted_expected_revenue", "sum"),
        )
        .sort_values(
            ["quarter", "territory_id", "stage_id"], kind="stable"
        )
        .reset_index(drop=True)
    )
    summary["total_amount"] = summary["total_amount"].round(2)
    summary["total_weighted_pipeline"] = summary[
        "total_weighted_pipeline"
    ].round(2)
    summary["snapshot_date"] = forecast["snapshot_date"].max()

    return forecast, summary


def run(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> tuple[Path, Path]:
    """Read raw data, build forecasts, and write processed CSV files."""
    raw_dir = Path(raw_dir)
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    snapshot = pd.read_csv(raw_dir / "forecast_snapshot.csv")
    stages = pd.read_csv(raw_dir / "stage.csv")
    opportunities = pd.read_csv(raw_dir / "opportunity.csv")
    history = pd.read_csv(raw_dir / "stage_history.csv")
    activity = pd.read_csv(raw_dir / "activity.csv")

    detail, summary = build_forecast(
        snapshot=snapshot,
        stages=stages,
        opportunities=opportunities,
        stage_history=history,
        activity=activity,
    )

    detail_path = processed_dir / "forecast_detail.csv"
    summary_path = processed_dir / "forecast_summary.csv"
    detail.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"Forecast detail saved to {detail_path}")
    print(f"Forecast summary saved to {summary_path}")
    return detail_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build baseline and adjusted sales forecasts."
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
        help="Directory receiving forecast output CSV files.",
    )
    args = parser.parse_args()
    run(args.raw_dir, args.processed_dir)


if __name__ == "__main__":
    main()