
import pandas as pd
import pytest

from src.forecast import build_forecast


def _inputs():
    snapshot = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "FCST-1",
                "snapshot_date": "2026-01-31",
                "opportunity_id": "OPP-1",
                "stage_id": "STAGE-1",
                "amount": 1000,
            },
            {
                "forecast_snapshot_id": "FCST-2",
                "snapshot_date": "2026-01-31",
                "opportunity_id": "OPP-2",
                "stage_id": "STAGE-1",
                "amount": 1000,
            },
        ]
    )

    stages = pd.DataFrame(
        [
            {
                "stage_id": "STAGE-1",
                "stage_name": "Proposal",
                "default_probability": 0.50,
            },
            {
                "stage_id": "STAGE-2",
                "stage_name": "Negotiation",
                "default_probability": 0.60,
            },
        ]
    )

    opportunities = pd.DataFrame(
        [
            {
                "opportunity_id": "OPP-1",
                "territory_id": "TER-1",
                "closed_date": None,
                "outcome": "Open",
            },
            {
                "opportunity_id": "OPP-2",
                "territory_id": "TER-1",
                "closed_date": None,
                "outcome": "Open",
            },
        ]
    )

    history = pd.DataFrame(
        [
            {
                "opportunity_id": "OPP-1",
                "to_stage_id": "STAGE-1",
                "changed_at": "2026-01-01",
            },
            {
                "opportunity_id": "OPP-2",
                "to_stage_id": "STAGE-1",
                "changed_at": "2026-01-25",
            },
        ]
    )

    activity = pd.DataFrame(
        [
            {
                "opportunity_id": "OPP-1",
                "activity_type": "Call",
                "activity_date": "2026-01-20",
                "outcome": "Completed",
            },
            {
                "opportunity_id": "OPP-1",
                "activity_type": "Meeting",
                "activity_date": "2026-01-22",
                "outcome": "Completed",
            },
            {
                "opportunity_id": "OPP-1",
                "activity_type": "Email",
                "activity_date": "2026-01-25",
                "outcome": "Completed",
            },
        ]
    )

    return snapshot, stages, opportunities, history, activity


def test_old_stage_age_reduces_adjusted_probability():
    snapshot, stages, opportunities, history, activity = _inputs()

    detail, _ = build_forecast(
        snapshot, stages, opportunities, history, activity
    )

    rows = detail.set_index("opportunity_id")

    assert rows.loc["OPP-1", "stage_age_days"] == 30
    assert rows.loc["OPP-2", "stage_age_days"] == 6
    assert rows.loc["OPP-1", "age_factor"] == pytest.approx(0.80)
    assert rows.loc["OPP-2", "age_factor"] == pytest.approx(1.00)


def test_no_recent_activity_reduces_probability_and_flags_stale():
    snapshot, stages, opportunities, history, activity = _inputs()

    detail, _ = build_forecast(
        snapshot, stages, opportunities, history, activity
    )

    rows = detail.set_index("opportunity_id")

    assert rows.loc["OPP-2", "activity_count_30d"] == 0
    assert rows.loc["OPP-2", "activity_factor"] == pytest.approx(0.80)
    assert bool(rows.loc["OPP-2", "adjusted_is_stale"]) is True


def test_three_or_more_recent_activities_increase_probability():
    snapshot, stages, opportunities, history, activity = _inputs()

    detail, _ = build_forecast(
        snapshot, stages, opportunities, history, activity
    )

    rows = detail.set_index("opportunity_id")

    assert rows.loc["OPP-1", "activity_count_30d"] == 3
    assert rows.loc["OPP-1", "activity_factor"] == pytest.approx(1.10)


def test_historical_stage_rate_uses_last_pre_close_stage():
    snapshot, stages, opportunities, history, activity = _inputs()

    opportunities = pd.concat(
        [
            opportunities,
            pd.DataFrame(
                [
                    {
                        "opportunity_id": "PAST-WON",
                        "territory_id": "TER-1",
                        "closed_date": "2026-01-15",
                        "outcome": "Won",
                    },
                    {
                        "opportunity_id": "PAST-LOST",
                        "territory_id": "TER-1",
                        "closed_date": "2026-01-20",
                        "outcome": "Lost",
                    },
                ]
            ),
        ],
        ignore_index=True,
    )

    history = pd.concat(
        [
            history,
            pd.DataFrame(
                [
                    {
                        "opportunity_id": "PAST-WON",
                        "to_stage_id": "STAGE-1",
                        "changed_at": "2026-01-05",
                    },
                    {
                        "opportunity_id": "PAST-WON",
                        "to_stage_id": "STAGE-2",
                        "changed_at": "2026-01-14",
                    },
                    {
                        "opportunity_id": "PAST-LOST",
                        "to_stage_id": "STAGE-1",
                        "changed_at": "2026-01-10",
                    },
                ]
            ),
        ],
        ignore_index=True,
    )

    historical_snapshots = pd.DataFrame(
        [
            {
                "forecast_snapshot_id": "PAST-FCST-1",
                "snapshot_date": "2026-01-05",
                "opportunity_id": "PAST-WON",
                "stage_id": "STAGE-1",
                "amount": 1000,
            },
            {
                "forecast_snapshot_id": "PAST-FCST-2",
                "snapshot_date": "2026-01-14",
                "opportunity_id": "PAST-WON",
                "stage_id": "STAGE-2",
                "amount": 1000,
            },
            {
                "forecast_snapshot_id": "PAST-FCST-3",
                "snapshot_date": "2026-01-10",
                "opportunity_id": "PAST-LOST",
                "stage_id": "STAGE-1",
                "amount": 1000,
            },
        ]
    )

    detail, _ = build_forecast(
        snapshot=snapshot,
        stages=stages,
        opportunities=opportunities,
        stage_history=history,
        activity=activity,
        forecast_snapshots=historical_snapshots,
    )

    rows = detail.set_index("opportunity_id")

    # PAST-WON's last pre-close stage was Negotiation (STAGE-2).
    # PAST-LOST's last pre-close stage was Proposal (STAGE-1).
    # Therefore Proposal's historical win rate must be zero,
    # not 50% from counting every stage the won deal reached.
    assert rows.loc["OPP-1", "historical_stage_win_rate"] == pytest.approx(
        0.0
    )
    assert rows.loc["OPP-2", "historical_stage_win_rate"] == pytest.approx(
        0.0
    )


def test_future_closures_and_activities_do_not_change_snapshot_forecast():
    snapshot, stages, opportunities, history, activity = _inputs()

    before, _ = build_forecast(
        snapshot, stages, opportunities, history, activity
    )

    future_opportunity = pd.DataFrame(
        [
            {
                "opportunity_id": "FUTURE-WON",
                "territory_id": "TER-1",
                "closed_date": "2026-02-10",
                "outcome": "Won",
            },
        ]
    )

    future_history = pd.DataFrame(
        [
            {
                "opportunity_id": "FUTURE-WON",
                "to_stage_id": "STAGE-1",
                "changed_at": "2026-02-01",
            },
        ]
    )

    future_activity = pd.DataFrame(
        [
            {
                "opportunity_id": "OPP-2",
                "activity_type": "Meeting",
                "activity_date": "2026-02-01",
                "outcome": "Completed",
            },
        ]
    )

    after, _ = build_forecast(
        snapshot,
        stages,
        pd.concat(
            [opportunities, future_opportunity],
            ignore_index=True,
        ),
        pd.concat(
            [history, future_history],
            ignore_index=True,
        ),
        pd.concat(
            [activity, future_activity],
            ignore_index=True,
        ),
    )

    columns = [
        "historical_stage_win_rate",
        "stage_age_days",
        "activity_count_30d",
        "adjusted_probability",
    ]

    pd.testing.assert_frame_equal(
        before[columns],
        after[columns],
    )
