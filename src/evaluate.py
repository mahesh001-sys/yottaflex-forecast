"""Compare baseline and adjusted forecast probabilities against final outcomes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


def _parse_utc_as_naive(series: pd.Series) -> pd.Series:
    """Parse dates consistently and remove timezone information."""
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None)


def _normalise_outcome(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def _brier_score(actual: pd.Series, predicted: pd.Series) -> float:
    """Lower Brier score indicates better probability accuracy."""
    return float(((predicted - actual) ** 2).mean())


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
    missing_forecast = required_forecast_columns - set(forecast_detail.columns)
    if missing_forecast:
        raise ValueError(
            "forecast_detail is missing required columns: "
            f"{sorted(missing_forecast)}. Run `python -m src.forecast` first."
        )

    required_opportunity_columns = {
        "opportunity_id",
        "outcome",
        "closed_date",
    }
    missing_opportunities = required_opportunity_columns - set(opportunities.columns)
    if missing_opportunities:
        raise ValueError(
            "opportunities is missing required columns: "
            f"{sorted(missing_opportunities)}."
        )

    closed = opportunities.copy()
    closed["outcome_normalised"] = _normalise_outcome(closed["outcome"])
    closed = closed[
        closed["outcome_normalised"].isin(
            {"WON", "LOST", "CLOSED WON", "CLOSED LOST"}
        )
    ].copy()

    if closed.empty:
        raise ValueError("No closed Won/Lost opportunities were found for evaluation.")

    if closed["opportunity_id"].duplicated().any():
        raise ValueError(
            "opportunity.csv contains duplicate IDs among closed opportunities."
        )

    closed["closed_date_parsed"] = _parse_utc_as_naive(closed["closed_date"])
    closed["actual"] = closed["outcome_normalised"].isin(
        {"WON", "CLOSED WON"}
    ).astype(float)

    forecasts = forecast_detail.copy()
    forecasts["snapshot_date_parsed"] = _parse_utc_as_naive(
        forecasts["snapshot_date"]
    )

    # Attach each opportunity's close date and outcome to its forecast snapshots.
    candidates = forecasts.merge(
        closed[
            [
                "opportunity_id",
                "closed_date_parsed",
                "actual",
            ]
        ],
        on="opportunity_id",
        how="inner",
        validate="many_to_one",
    )

    # Keep only forecasts made strictly before the opportunity closed.
    candidates = candidates[
        candidates["snapshot_date_parsed"].notna()
        & candidates["closed_date_parsed"].notna()
        & (
            candidates["snapshot_date_parsed"]
            < candidates["closed_date_parsed"]
        )
    ].copy()

    if candidates.empty:
        raise ValueError(
            "No closed opportunities had a valid forecast snapshot before close."
        )

    # Select the most recent eligible snapshot for each opportunity.
    scored = (
        candidates.sort_values(
            ["opportunity_id", "snapshot_date_parsed"],
            kind="mergesort",
        )
        .drop_duplicates(subset=["opportunity_id"], keep="last")
        .copy()
    )

    if scored.empty:
        raise ValueError(
            "No forecast opportunities matched closed outcomes in opportunity.csv."
        )

    results = []
    for model_name, probability_column in [
        ("baseline", "baseline_probability"),
        ("adjusted", "adjusted_probability"),
    ]:
        valid = scored[["actual", probability_column]].dropna()
        if valid.empty:
            score = float("nan")
        else:
            score = _brier_score(
                valid["actual"],
                valid[probability_column].clip(0.0, 1.0),
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


def run() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    forecast_path = PROCESSED_DIR / "forecast_detail.csv"
    opportunities_path = RAW_DIR / "opportunity.csv"

    if not forecast_path.exists():
        raise FileNotFoundError(
            f"{forecast_path} does not exist. Run `python -m src.forecast` first."
        )

    forecast_detail = pd.read_csv(forecast_path)
    opportunities = pd.read_csv(opportunities_path)

    results = evaluate_forecasts(forecast_detail, opportunities)
    output_path = PROCESSED_DIR / "forecast_evaluation.csv"
    results.to_csv(output_path, index=False)

    print(results.to_string(index=False))
    print(f"\nEvaluation saved to {output_path}")


if __name__ == "__main__":
    run()