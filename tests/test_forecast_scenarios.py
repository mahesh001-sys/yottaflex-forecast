import pandas as pd
import pytest

from src.forecast import build_forecast
from src.scenarios import build_scenarios


def _worked_example_inputs():
    snapshot = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "FCST-A",
                "snapshot_date": "2026-01-31",
                "opportunity_id": "OPP-A",
                "stage_id": "STAGE-003",
                "amount": 10_000.00,
            },
            {
                "forecast_snapshot_id": "FCST-B",
                "snapshot_date": "2026-01-31",
                "opportunity_id": "OPP-B",
                "stage_id": "STAGE-004",
                "amount": 20_000.00,
            },
            {
                "forecast_snapshot_id": "FCST-C",
                "snapshot_date": "2026-01-31",
                "opportunity_id": "OPP-C",
                "stage_id": "STAGE-001",
                "amount": 5_000.00,
            },
        ]
    )

    stages = pd.DataFrame(
        [
            {
                "stage_id": "STAGE-001",
                "stage_name": "Prospecting",
                "default_probability": 0.10,
            },
            {
                "stage_id": "STAGE-003",
                "stage_name": "Proposal",
                "default_probability": 0.50,
            },
            {
                "stage_id": "STAGE-004",
                "stage_name": "Negotiation",
                "default_probability": 0.80,
            },
        ]
    )

    opportunities = pd.DataFrame(
        [
            {"opportunity_id": "OPP-A", "territory_id": "TER-1"},
            {"opportunity_id": "OPP-B", "territory_id": "TER-1"},
            {"opportunity_id": "OPP-C", "territory_id": "TER-2"},
        ]
    )

    return snapshot, stages, opportunities


def test_forecast_worked_example_totals_21500():
    snapshot, stages, opportunities = _worked_example_inputs()

    detail, summary = build_forecast(snapshot, stages, opportunities)

    assert detail["expected_revenue"].tolist() == [
        5_000.00,
        16_000.00,
        500.00,
    ]
    assert detail["expected_revenue"].sum() == pytest.approx(21_500.00)
    assert summary["total_weighted_pipeline"].sum() == pytest.approx(21_500.00)


def test_scenario_probability_adjustments_and_revenue():
    snapshot, stages, opportunities = _worked_example_inputs()
    forecast_detail, _ = build_forecast(snapshot, stages, opportunities)

    detail, _ = build_scenarios(forecast_detail)

    row_a = detail[
        detail["opportunity_id"].eq("OPP-A")
    ].set_index("scenario")

    assert row_a.loc["Pessimistic", "scenario_probability"] == pytest.approx(0.375)
    assert row_a.loc["Baseline", "scenario_probability"] == pytest.approx(0.50)
    assert row_a.loc["Optimistic", "scenario_probability"] == pytest.approx(0.60)

    assert row_a.loc["Pessimistic", "scenario_expected_revenue"] == pytest.approx(
        3_187.50
    )
    assert row_a.loc["Baseline", "scenario_expected_revenue"] == pytest.approx(
        5_000.00
    )
    assert row_a.loc["Optimistic", "scenario_expected_revenue"] == pytest.approx(
        6_000.00
    )


def test_optimistic_probability_is_capped_at_one():
    forecast_detail = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "FCST-WON",
                "snapshot_date": "2026-01-31",
                "quarter": "2026Q1",
                "opportunity_id": "OPP-WON",
                "territory_id": "TER-1",
                "stage_id": "STAGE-005",
                "stage_name": "Closed Won",
                "amount": 10_000.00,
                "stage_probability": 1.00,
                "expected_revenue": 10_000.00,
            }
        ]
    )

    detail, _ = build_scenarios(forecast_detail)

    optimistic = detail[detail["scenario"].eq("Optimistic")].iloc[0]
    assert optimistic["scenario_probability"] == pytest.approx(1.00)
    assert optimistic["scenario_expected_revenue"] == pytest.approx(10_000.00)


def test_scenario_detail_and_summary_reconcile():
    snapshot, stages, opportunities = _worked_example_inputs()
    forecast_detail, _ = build_forecast(snapshot, stages, opportunities)

    detail, summary = build_scenarios(forecast_detail)

    assert len(detail) == 3 * len(forecast_detail)

    detail_totals = detail.groupby("scenario")[
        "scenario_expected_revenue"
    ].sum()
    summary_totals = summary.groupby("scenario")[
        "total_weighted_pipeline"
    ].sum()

    pd.testing.assert_series_equal(
        detail_totals.sort_index(),
        summary_totals.sort_index(),
        check_names=False,
        check_dtype=False,
    )