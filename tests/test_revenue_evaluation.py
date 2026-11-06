
import pandas as pd
import pytest

from src.evaluate import (
    evaluate_latest_opportunity_revenue_accuracy,
    evaluate_revenue_accuracy,
)


def test_revenue_accuracy_has_expected_error_and_bias():
    forecasts = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "s1",
                "snapshot_date": "2026-01-01",
                "opportunity_id": "A",
                "expected_revenue": 120.0,
                "adjusted_expected_revenue": 110.0,
                "territory_id": "T1",
                "product": "P1",
                "owner_rep_id": "R1",
            },
            {
                "forecast_snapshot_id": "s1",
                "snapshot_date": "2026-01-01",
                "opportunity_id": "B",
                "expected_revenue": 80.0,
                "adjusted_expected_revenue": 90.0,
                "territory_id": "T1",
                "product": "P2",
                "owner_rep_id": "R2",
            },
        ]
    )

    opportunities = pd.DataFrame(
        [
            {
                "opportunity_id": "A",
                "outcome": "WON",
                "closed_date": "2026-01-31",
            },
            {
                "opportunity_id": "B",
                "outcome": "LOST",
                "closed_date": "2026-01-31",
            },
            # Not in the snapshot, so this opportunity must not be evaluated.
            {
                "opportunity_id": "C",
                "outcome": "WON",
                "closed_date": "2026-01-31",
            },
        ]
    )

    bookings = pd.DataFrame(
        [
            {"opportunity_id": "A", "booking_amount": 100.0},
            {"opportunity_id": "C", "booking_amount": 500.0},
        ]
    )

    accuracy, detail = evaluate_revenue_accuracy(
        forecasts,
        opportunities,
        bookings,
    )

    baseline = accuracy[
        (accuracy["model"] == "baseline")
        & (accuracy["horizon_bucket"] == "0-30 days")
        & (accuracy["segment_type"] == "overall")
    ].iloc[0]

    adjusted = accuracy[
        (accuracy["model"] == "adjusted")
        & (accuracy["horizon_bucket"] == "0-30 days")
        & (accuracy["segment_type"] == "overall")
    ].iloc[0]

    assert len(detail) == 4
    assert set(detail["opportunity_id"]) == {"A", "B"}

    assert baseline["expected_revenue"] == pytest.approx(200.0)
    assert baseline["actual_booked_revenue"] == pytest.approx(100.0)
    assert baseline["error"] == pytest.approx(100.0)
    assert baseline["absolute_error"] == pytest.approx(100.0)
    assert baseline["wape_pct"] == pytest.approx(100.0)
    assert baseline["bias_direction"] == "over-forecast"

    assert adjusted["expected_revenue"] == pytest.approx(200.0)
    assert adjusted["error"] == pytest.approx(100.0)
    assert adjusted["bias_pct"] == pytest.approx(100.0)


def test_revenue_accuracy_sums_multiple_booking_rows():
    forecasts = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "s1",
                "snapshot_date": "2026-01-01",
                "opportunity_id": "A",
                "expected_revenue": 100.0,
                "adjusted_expected_revenue": 100.0,
            }
        ]
    )

    opportunities = pd.DataFrame(
        [
            {
                "opportunity_id": "A",
                "outcome": "WON",
                "closed_date": "2026-01-10",
            }
        ]
    )

    bookings = pd.DataFrame(
        [
            {"opportunity_id": "A", "booking_amount": 40.0},
            {"opportunity_id": "A", "booking_amount": 60.0},
        ]
    )

    accuracy, _ = evaluate_revenue_accuracy(
        forecasts,
        opportunities,
        bookings,
    )

    overall = accuracy[
        accuracy["segment_type"] == "overall"
    ].iloc[0]

    assert overall["actual_booked_revenue"] == pytest.approx(100.0)
    assert overall["error"] == pytest.approx(0.0)
    assert overall["bias_direction"] == "exact"


def test_latest_opportunity_revenue_accuracy_uses_latest_pre_close_snapshot():
    forecasts = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "s1",
                "snapshot_date": "2026-01-01",
                "opportunity_id": "A",
                "expected_revenue": 100.0,
                "adjusted_expected_revenue": 90.0,
            },
            {
                "forecast_snapshot_id": "s2",
                "snapshot_date": "2026-01-20",
                "opportunity_id": "A",
                "expected_revenue": 150.0,
                "adjusted_expected_revenue": 140.0,
            },
            {
                # This snapshot is on the closing date and must be excluded.
                "forecast_snapshot_id": "s3",
                "snapshot_date": "2026-01-31",
                "opportunity_id": "A",
                "expected_revenue": 999.0,
                "adjusted_expected_revenue": 999.0,
            },
            {
                "forecast_snapshot_id": "s4",
                "snapshot_date": "2026-01-05",
                "opportunity_id": "B",
                "expected_revenue": 200.0,
                "adjusted_expected_revenue": 180.0,
            },
        ]
    )

    opportunities = pd.DataFrame(
        [
            {
                "opportunity_id": "A",
                "outcome": "WON",
                "closed_date": "2026-01-31",
            },
            {
                "opportunity_id": "B",
                "outcome": "LOST",
                "closed_date": "2026-01-20",
            },
        ]
    )

    bookings = pd.DataFrame(
        [
            {"opportunity_id": "A", "booking_amount": 100.0},
        ]
    )

    accuracy, detail = evaluate_latest_opportunity_revenue_accuracy(
        forecasts,
        opportunities,
        bookings,
    )

    # One selected snapshot per opportunity, expanded into two models.
    assert len(detail) == 4

    assert (
        detail.duplicated(
            ["opportunity_id", "model"]
        ).sum()
        == 0
    )

    # A must use s2, not s1 or the snapshot on its close date.
    opportunity_a = detail[
        detail["opportunity_id"] == "A"
    ]

    assert set(opportunity_a["forecast_snapshot_id"]) == {"s2"}
    assert set(opportunity_a["expected_revenue"]) == {150.0, 140.0}

    # B has only one valid pre-close snapshot.
    opportunity_b = detail[
        detail["opportunity_id"] == "B"
    ]

    assert set(opportunity_b["forecast_snapshot_id"]) == {"s4"}

    baseline = accuracy[
        (accuracy["model"] == "baseline")
        & (accuracy["segment_type"] == "overall")
    ].iloc[0]

    adjusted = accuracy[
        (accuracy["model"] == "adjusted")
        & (accuracy["segment_type"] == "overall")
    ].iloc[0]

    assert baseline["expected_revenue"] == pytest.approx(350.0)
    assert baseline["actual_booked_revenue"] == pytest.approx(100.0)
    assert baseline["error"] == pytest.approx(250.0)

    assert adjusted["expected_revenue"] == pytest.approx(320.0)
    assert adjusted["actual_booked_revenue"] == pytest.approx(100.0)
    assert adjusted["error"] == pytest.approx(220.0)
