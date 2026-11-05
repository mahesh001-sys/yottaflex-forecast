"""Evaluate forecast probabilities and historical snapshot revenue accuracy."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

CLOSED_OUTCOMES = {"WON", "LOST", "CLOSED WON", "CLOSED LOST"}
WON_OUTCOMES = {"WON", "CLOSED WON"}

HORIZON_BUCKETS = [
    (0, 30, "0-30 days"),
    (31, 60, "31-60 days"),
    (61, 90, "61-90 days"),
    (91, 180, "91-180 days"),
    (181, None, "181+ days"),
]


def _parse_utc_as_naive(series: pd.Series) -> pd.Series:
    """Parse dates consistently and remove timezone information."""
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None)


def _normalise_outcome(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def _brier_score(actual: pd.Series, predicted: pd.Series) -> float:
    """Lower Brier score indicates better probability accuracy."""
    return float(((predicted - actual) ** 2).mean())


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    frame_name: str,
) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"{frame_name} is missing required columns: {sorted(missing)}."
        )


def evaluate_forecasts(
    forecast_detail: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate the latest pre-close forecast for each closed opportunity."""
    required_forecast_columns = {
        "opportunity_id",
        "snapshot_date",
        "baseline_probability",
        "adjusted_probability",
    }
    _require_columns(forecast_detail, required_forecast_columns, "forecast_detail")

    required_opportunity_columns = {
        "opportunity_id",
        "outcome",
        "closed_date",
    }
    _require_columns(opportunities, required_opportunity_columns, "opportunities")

    closed = opportunities.copy()
    closed["outcome_normalised"] = _normalise_outcome(closed["outcome"])
    closed = closed[closed["outcome_normalised"].isin(CLOSED_OUTCOMES)].copy()

    if closed.empty:
        raise ValueError("No closed Won/Lost opportunities were found for evaluation.")
    if closed["opportunity_id"].duplicated().any():
        raise ValueError(
            "opportunity.csv contains duplicate IDs among closed opportunities."
        )

    closed["closed_date_parsed"] = _parse_utc_as_naive(closed["closed_date"])
    closed["actual"] = closed["outcome_normalised"].isin(WON_OUTCOMES).astype(float)

    forecasts = forecast_detail.copy()
    forecasts["snapshot_date_parsed"] = _parse_utc_as_naive(
        forecasts["snapshot_date"]
    )

    candidates = forecasts.merge(
        closed[["opportunity_id", "closed_date_parsed", "actual"]],
        on="opportunity_id",
        how="inner",
        validate="many_to_one",
    )
    candidates = candidates[
        candidates["snapshot_date_parsed"].notna()
        & candidates["closed_date_parsed"].notna()
        & (candidates["snapshot_date_parsed"] < candidates["closed_date_parsed"])
    ].copy()

    if candidates.empty:
        raise ValueError(
            "No closed opportunities had a valid forecast snapshot before close."
        )

    scored = (
        candidates.sort_values(
            ["opportunity_id", "snapshot_date_parsed"],
            kind="mergesort",
        )
        .drop_duplicates(subset=["opportunity_id"], keep="last")
        .copy()
    )

    results = []
    for model_name, probability_column in [
        ("baseline", "baseline_probability"),
        ("adjusted", "adjusted_probability"),
    ]:
        valid = scored[["actual", probability_column]].dropna()
        score = (
            _brier_score(
                valid["actual"],
                valid[probability_column].clip(0.0, 1.0),
            )
            if not valid.empty
            else float("nan")
        )
        results.append(
            {
                "model": model_name,
                "evaluated_opportunities": len(valid),
                "brier_score": score,
            }
        )

    results_frame = pd.DataFrame(results)
    results_frame["lower_is_better"] = True
    return results_frame


def _horizon_bucket(days: int) -> str:
    for lower, upper, label in HORIZON_BUCKETS:
        if days >= lower and (upper is None or days <= upper):
            return label
    return "Unknown"


def evaluate_revenue_accuracy(
    forecast_detail: pd.DataFrame,
    opportunities: pd.DataFrame,
    historical_bookings: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Evaluate baseline and adjusted expected revenue for each historical snapshot.

    Error is expected revenue minus actual booked revenue: positive means
    over-forecast, negative means under-forecast. Aggregate WAPE and bias are
    percentages of total actual booked revenue.
    """
    _require_columns(
        forecast_detail,
        {
            "forecast_snapshot_id",
            "snapshot_date",
            "opportunity_id",
            "expected_revenue",
            "adjusted_expected_revenue",
        },
        "forecast_detail",
    )
    _require_columns(
        opportunities,
        {"opportunity_id", "outcome", "closed_date"},
        "opportunities",
    )
    _require_columns(
        historical_bookings,
        {"opportunity_id", "booking_amount"},
        "historical_bookings",
    )

    closed = opportunities.copy()
    closed["outcome_normalised"] = _normalise_outcome(closed["outcome"])
    closed = closed[closed["outcome_normalised"].isin(CLOSED_OUTCOMES)].copy()
    closed["closed_date_parsed"] = _parse_utc_as_naive(closed["closed_date"])
    closed = closed[closed["closed_date_parsed"].notna()].copy()

    if closed["opportunity_id"].duplicated().any():
        raise ValueError(
            "opportunity.csv contains duplicate IDs among closed opportunities."
        )

    bookings = historical_bookings.copy()
    bookings["booking_amount"] = pd.to_numeric(
        bookings["booking_amount"], errors="coerce"
    )
    bookings = bookings.dropna(subset=["opportunity_id", "booking_amount"])

    booking_totals = (
        bookings.groupby("opportunity_id", as_index=False)["booking_amount"]
        .sum()
        .rename(columns={"booking_amount": "actual_booked_revenue"})
    )

    # Start from snapshot rows so opportunities absent from a snapshot are excluded.
    detail = forecast_detail.copy()
    detail["snapshot_date_parsed"] = _parse_utc_as_naive(detail["snapshot_date"])
    detail = detail.merge(
        closed[["opportunity_id", "closed_date_parsed"]],
        on="opportunity_id",
        how="inner",
        validate="many_to_one",
    )
    detail = detail[
        detail["snapshot_date_parsed"].notna()
        & (detail["snapshot_date_parsed"] < detail["closed_date_parsed"])
    ].copy()

    if detail.empty:
        raise ValueError("No closed opportunities have valid pre-close snapshot rows.")

    detail["horizon_days"] = (
        detail["closed_date_parsed"] - detail["snapshot_date_parsed"]
    ).dt.days
    detail["horizon_bucket"] = detail["horizon_days"].map(_horizon_bucket)

    detail = detail.merge(
        booking_totals,
        on="opportunity_id",
        how="left",
        validate="many_to_one",
    )
    detail["actual_booked_revenue"] = detail["actual_booked_revenue"].fillna(0.0)

    # Normalise segment fields before producing the row-level output.
    segment_columns = ["territory_id", "product", "owner_rep_id"]
    for column in segment_columns:
        if column not in detail.columns:
            detail[column] = "Unknown"
        detail[column] = detail[column].fillna("Unknown").astype(str)

    detail = detail.rename(columns={"owner_rep_id": "rep_id"})

    model_rows = []
    for model_name, expected_column in [
        ("baseline", "expected_revenue"),
        ("adjusted", "adjusted_expected_revenue"),
    ]:
        expected = pd.to_numeric(detail[expected_column], errors="coerce")
        valid = detail.loc[expected.notna()].copy()
        valid["model"] = model_name
        valid["expected_revenue"] = expected.loc[valid.index]
        valid["error"] = (
            valid["expected_revenue"] - valid["actual_booked_revenue"]
        )
        valid["absolute_error"] = valid["error"].abs()
        valid["bias_direction"] = valid["error"].map(
            lambda value: (
                "over-forecast"
                if value > 0
                else "under-forecast"
                if value < 0
                else "exact"
            )
        )
        model_rows.append(valid)

    detail_result = pd.concat(model_rows, ignore_index=True)

    detail_columns = [
        "forecast_snapshot_id",
        "snapshot_date",
        "opportunity_id",
        "closed_date_parsed",
        "horizon_days",
        "horizon_bucket",
        "territory_id",
        "product",
        "rep_id",
        "model",
        "expected_revenue",
        "actual_booked_revenue",
        "error",
        "absolute_error",
        "bias_direction",
    ]
    detail_result = detail_result[detail_columns].rename(
        columns={"closed_date_parsed": "closed_date"}
    )

    aggregate_rows = []
    segment_specs = [
        ("overall", None),
        ("territory", "territory_id"),
        ("product", "product"),
        ("rep", "rep_id"),
    ]

    for (model_name, horizon), horizon_frame in detail_result.groupby(
        ["model", "horizon_bucket"], dropna=False
    ):
        for segment_type, segment_column in segment_specs:
            if segment_column is None:
                groups = [("ALL", horizon_frame)]
            else:
                groups = horizon_frame.groupby(segment_column, dropna=False)

            for segment_value, group in groups:
                actual_total = float(group["actual_booked_revenue"].sum())
                expected_total = float(group["expected_revenue"].sum())
                net_error = float(group["error"].sum())
                absolute_error = float(group["absolute_error"].sum())

                aggregate_rows.append(
                    {
                        "model": model_name,
                        "horizon_bucket": horizon,
                        "segment_type": segment_type,
                        "segment_value": str(segment_value),
                        "evaluated_snapshot_rows": len(group),
                        "expected_revenue": expected_total,
                        "actual_booked_revenue": actual_total,
                        "error": net_error,
                        "absolute_error": absolute_error,
                        "wape_pct": (
                            absolute_error / actual_total * 100.0
                            if actual_total != 0
                            else float("nan")
                        ),
                        "bias_pct": (
                            net_error / actual_total * 100.0
                            if actual_total != 0
                            else float("nan")
                        ),
                        "bias_direction": (
                            "over-forecast"
                            if net_error > 0
                            else "under-forecast"
                            if net_error < 0
                            else "exact"
                        ),
                    }
                )

    return pd.DataFrame(aggregate_rows), detail_result


def run() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    forecast_path = PROCESSED_DIR / "forecast_detail.csv"
    opportunities_path = RAW_DIR / "opportunity.csv"
    bookings_path = RAW_DIR / "historical_booking.csv"

    if not forecast_path.exists():
        raise FileNotFoundError(
            f"{forecast_path} does not exist. Run `python -m src.forecast` first."
        )
    if not opportunities_path.exists():
        raise FileNotFoundError(f"{opportunities_path} does not exist.")
    if not bookings_path.exists():
        raise FileNotFoundError(f"{bookings_path} does not exist.")

    forecast_detail = pd.read_csv(forecast_path, low_memory=False)
    opportunities = pd.read_csv(opportunities_path, low_memory=False)
    historical_bookings = pd.read_csv(bookings_path, low_memory=False)

    # Preserve the existing probability evaluation and its output.
    brier_results = evaluate_forecasts(forecast_detail, opportunities)
    brier_path = PROCESSED_DIR / "forecast_evaluation.csv"
    brier_results.to_csv(brier_path, index=False)

    accuracy, detail = evaluate_revenue_accuracy(
        forecast_detail,
        opportunities,
        historical_bookings,
    )
    accuracy_path = PROCESSED_DIR / "forecast_accuracy.csv"
    detail_path = PROCESSED_DIR / "forecast_evaluation_detail.csv"
    accuracy.to_csv(accuracy_path, index=False)
    detail.to_csv(detail_path, index=False)

    print(brier_results.to_string(index=False))
    print(f"\nBrier evaluation saved to {brier_path}")
    print(f"Revenue accuracy saved to {accuracy_path}")
    print(f"Revenue detail saved to {detail_path}")


if __name__ == "__main__":
    run()