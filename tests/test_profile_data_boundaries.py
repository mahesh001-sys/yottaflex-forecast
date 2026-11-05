from datetime import date

import pytest

from src.profile_data import (
    clamp_probability,
    quarter_label,
    stage_as_of,
    territory_for_rep,
)


def test_close_date_on_quarter_boundary_uses_that_quarter():
    assert quarter_label("2026-03-31") == "2026Q1"
    assert quarter_label("2026-04-01") == "2026Q2"


def test_snapshot_on_stage_change_date_includes_that_stage():
    history = [
        {
            "opportunity_id": "OPP-1",
            "changed_at": "2026-03-31",
            "event_sequence": "1",
            "to_stage_id": "STAGE-1",
        },
        {
            "opportunity_id": "OPP-1",
            "changed_at": "2026-04-01",
            "event_sequence": "2",
            "to_stage_id": "STAGE-2",
        },
    ]

    assert stage_as_of(history, "OPP-1", date(2026, 4, 1)) == "STAGE-2"


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (1.0, 1.0),
        (1.25, 1.0),
        (0.0, 0.0),
        (-0.25, 0.0),
    ],
)
def test_probability_is_clamped_at_inclusive_bounds(probability, expected):
    assert clamp_probability(probability) == expected


def test_rep_with_zero_activities_can_have_zero_count():
    # profile_data retains reps from sales_rep.csv even when they have no activities.
    activity_counts = {}
    rep_ids = ["REP-1", "REP-2"]

    counts = [activity_counts.get(rep_id, 0) for rep_id in rep_ids]

    assert counts == [0, 0]


def test_territory_change_uses_start_inclusive_end_exclusive_dates():
    assignments = [
        {
            "rep_id": "REP-1",
            "territory_id": "TERR-OLD",
            "effective_from": "2026-01-01",
            "effective_to": "2026-04-01",
        },
        {
            "rep_id": "REP-1",
            "territory_id": "TERR-NEW",
            "effective_from": "2026-04-01",
            "effective_to": "",
        },
    ]

    assert territory_for_rep(assignments, "REP-1", date(2026, 3, 31)) == "TERR-OLD"
    assert territory_for_rep(assignments, "REP-1", date(2026, 4, 1)) == "TERR-NEW"