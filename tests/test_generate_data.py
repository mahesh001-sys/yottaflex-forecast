
import hashlib
import re

import pandas as pd

from src.generate_data import generate_dataset


SEED = 20261022


def file_sha256(path):
    """Return the SHA-256 checksum of a generated CSV file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        assert data[table][primary_keys[table]].map(
            lambda x: bool(re.match(pattern, x))
        ).all()

    for table, key in primary_keys.items():
        assert data[table][key].is_unique


def test_foreign_keys_and_dates(tmp_path):
    data = generate_dataset("starter", tmp_path / "one")

    assert set(data["account"]["territory_id"]).issubset(
        set(data["territory"]["territory_id"])
    )

    assignments = data["rep_territory_assignment"]
    assert set(assignments["rep_id"]).issubset(
        set(data["sales_rep"]["rep_id"])
    )
    assert set(assignments["territory_id"]).issubset(
        set(data["territory"]["territory_id"])
    )

    opp = data["opportunity"]
    assert set(opp["account_id"]).issubset(
        set(data["account"]["account_id"])
    )
    assert set(opp["owner_rep_id"]).issubset(
        set(data["sales_rep"]["rep_id"])
    )
    assert set(opp["territory_id"]).issubset(
        set(data["territory"]["territory_id"])
    )

    history = data["stage_history"]
    assert set(history["opportunity_id"]).issubset(
        set(opp["opportunity_id"])
    )

    stage_ids = set(data["stage"]["stage_id"])
    assert set(history["to_stage_id"]).issubset(stage_ids)
    assert set(history["from_stage_id"].dropna()).issubset(stage_ids)

    assert (
        pd.to_datetime(opp["expected_close_date"])
        >= pd.to_datetime(opp["created_date"])
    ).all()


def test_same_seed_same_output(tmp_path):
    first = generate_dataset(
        "starter", tmp_path / "first", seed=SEED
    )
    second = generate_dataset(
        "starter", tmp_path / "second", seed=SEED
    )

    assert list(first) == list(second)

    for table in first:
        pd.testing.assert_frame_equal(first[table], second[table])

        first_file = tmp_path / "first" / f"{table}.csv"
        second_file = tmp_path / "second" / f"{table}.csv"

        assert first_file.read_bytes() == second_file.read_bytes()


def test_full_scale_reproducibility_with_sha256(tmp_path):
    """Verify full-scale generation is reproducible across two runs."""

    first_dir = tmp_path / "full_run_one"
    second_dir = tmp_path / "full_run_two"

    first = generate_dataset("full", first_dir, seed=SEED)
    second = generate_dataset("full", second_dir, seed=SEED)

    # Both runs must generate the same tables in the same order.
    assert list(first) == list(second)

    first_results = {}
    second_results = {}

    for table in first:
        first_file = first_dir / f"{table}.csv"
        second_file = second_dir / f"{table}.csv"

        first_results[table] = {
            "row_count": len(first[table]),
            "sha256": file_sha256(first_file),
        }

        second_results[table] = {
            "row_count": len(second[table]),
            "sha256": file_sha256(second_file),
        }

    # Compare row counts and SHA-256 checksums for every table.
    assert first_results == second_results

    # Confirm that all expected generated CSV files exist.
    assert len(first_results) == 11
