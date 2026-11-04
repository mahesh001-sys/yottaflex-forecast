import re
import pandas as pd

from src.generate_data import generate_dataset


def test_ids_and_primary_key_uniqueness(tmp_path):
    data = generate_dataset("starter", tmp_path / "one")
    patterns = {
        "territory": r"^TER-\d{4}$",
        "sales_rep": r"^REP-\d{6}$",
        "account": r"^ACC-\d{6}$",
        "opportunity": r"^OPP-202[56]-\d{6}$",
    }
    primary_keys = {
        "territory": "territory_id",
        "stage": "stage_id",
        "sales_rep": "rep_id",
        "account": "account_id",
        "rep_territory_assignment": "assignment_id",
        "opportunity": "opportunity_id",
        "stage_history": "stage_history_id",
    }
    for table, pattern in patterns.items():
        assert data[table][primary_keys[table]].map(lambda x: bool(re.match(pattern, x))).all()
    for table, key in primary_keys.items():
        assert data[table][key].is_unique


def test_foreign_keys_and_dates(tmp_path):
    data = generate_dataset("starter", tmp_path / "one")
    assert set(data["account"]["territory_id"]).issubset(set(data["territory"]["territory_id"]))
    assignments = data["rep_territory_assignment"]
    assert set(assignments["rep_id"]).issubset(set(data["sales_rep"]["rep_id"]))
    assert set(assignments["territory_id"]).issubset(set(data["territory"]["territory_id"]))
    opp = data["opportunity"]
    assert set(opp["account_id"]).issubset(set(data["account"]["account_id"]))
    assert set(opp["owner_rep_id"]).issubset(set(data["sales_rep"]["rep_id"]))
    assert set(opp["territory_id"]).issubset(set(data["territory"]["territory_id"]))
    history = data["stage_history"]
    assert set(history["opportunity_id"]).issubset(set(opp["opportunity_id"]))
    stage_ids = set(data["stage"]["stage_id"])
    assert set(history["to_stage_id"]).issubset(stage_ids)
    assert set(history["from_stage_id"].dropna()).issubset(stage_ids)
    assert (pd.to_datetime(opp["expected_close_date"]) >= pd.to_datetime(opp["created_date"])).all()


def test_same_seed_same_output(tmp_path):
    first = generate_dataset("starter", tmp_path / "first")
    second = generate_dataset("starter", tmp_path / "second")
    assert list(first) == list(second)
    for table in first:
        pd.testing.assert_frame_equal(first[table], second[table])
        assert (tmp_path / "first" / f"{table}.csv").read_bytes() == (
            tmp_path / "second" / f"{table}.csv"
        ).read_bytes()


def test_some_reps_change_territory_mid_period(tmp_path):
    data = generate_dataset("starter", tmp_path / "one")
    assignments = data["rep_territory_assignment"]
    assert assignments.groupby("rep_id").size().gt(1).any()
    assert assignments["effective_to"].notna().any()
