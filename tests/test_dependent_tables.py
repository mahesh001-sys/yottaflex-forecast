import pandas as pd
import csv
import hashlib

from src.generate_data import generate_dataset, STAGE_ID


def test_booking_rows_reconcile_to_won_opportunities():
    data = generate_dataset("starter", out="/tmp/unused-generator-output")
    opp = data["opportunity"].set_index("opportunity_id")
    bookings = data["historical_booking"]
    assert set(bookings["opportunity_id"]) == set(opp.loc[opp.outcome == "Won"].index)
    for row in bookings.itertuples(index=False):
        opportunity = opp.loc[row.opportunity_id]
        assert float(row.booking_amount) == float(opportunity.amount)
        assert row.booking_date == opportunity.closed_date


def test_snapshot_stage_uses_latest_history_known_as_of_snapshot():
    data = generate_dataset("starter", out="/tmp/unused-generator-output")
    history = data["stage_history"].copy()
    history["changed_at"] = pd.to_datetime(history["changed_at"], utc=True).dt.tz_localize(None)
    snapshots = data["forecast_snapshot"]
    for row in snapshots.itertuples(index=False):
        snapshot_date = pd.Timestamp(row.snapshot_date) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        known = history[(history.opportunity_id == row.opportunity_id) & (history.changed_at <= snapshot_date)]
        assert not known.empty
        latest = known.sort_values(["changed_at", "event_sequence"]).iloc[-1]
        assert row.stage_id == latest.to_stage_id
        assert pd.Timestamp(latest.changed_at).date() <= pd.Timestamp(row.snapshot_date).date()


def test_dependent_tables_use_valid_parent_ids_and_stage_transitions():
    data = generate_dataset("starter", out="/tmp/unused-generator-output")
    opp_ids = set(data["opportunity"].opportunity_id)
    rep_ids = set(data["sales_rep"].rep_id)
    history = data["stage_history"].sort_values(["opportunity_id", "event_sequence"])
    assert set(data["activity"].opportunity_id) <= opp_ids
    assert set(data["activity"].rep_id) <= rep_ids
    assert set(data["quota"].rep_id) <= rep_ids
    assert set(data["historical_booking"].opportunity_id) <= opp_ids
    assert set(data["forecast_snapshot"].opportunity_id) <= opp_ids
    for _, group in history.groupby("opportunity_id"):
        previous = None
        for row in group.itertuples(index=False):
            assert row.from_stage_id == previous
            previous = row.to_stage_id




def _csv_checksums_and_rows(directory):
    result = {}
    for path in sorted(directory.glob("*.csv")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            rows = sum(1 for _ in csv.DictReader(file))
        result[path.name] = {"row_count": rows, "sha256": digest}
    return result


def test_starter_dataset_is_reproducible(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    generate_dataset("starter", out=first_dir, seed=20261022)
    generate_dataset("starter", out=second_dir, seed=20261022)

    assert _csv_checksums_and_rows(first_dir) == _csv_checksums_and_rows(second_dir)