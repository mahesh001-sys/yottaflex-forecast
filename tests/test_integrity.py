import csv

from src.check_integrity import check_foreign_key, check_primary_key


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_primary_key_detects_duplicate(tmp_path):
    write_csv(
        tmp_path / "territory.csv",
        ["territory_id"],
        [{"territory_id": "T1"}, {"territory_id": "T1"}],
    )

    passed, checked, violations, detail = check_primary_key(
        tmp_path, "territory", "territory_id"
    )

    assert passed is False
    assert checked == 2
    assert violations == 1
    assert "duplicates=1" in detail


def test_primary_key_detects_blank_value(tmp_path):
    write_csv(
        tmp_path / "territory.csv",
        ["territory_id"],
        [{"territory_id": ""}],
    )

    passed, checked, violations, detail = check_primary_key(
        tmp_path, "territory", "territory_id"
    )

    assert passed is False
    assert checked == 1
    assert violations == 1
    assert "blank=1" in detail


def test_foreign_key_detects_missing_reference(tmp_path):
    write_csv(
        tmp_path / "sales_rep.csv",
        ["rep_id", "territory_id"],
        [{"rep_id": "R1", "territory_id": "T-MISSING"}],
    )
    write_csv(
        tmp_path / "territory.csv",
        ["territory_id"],
        [{"territory_id": "T1"}],
    )

    passed, checked, violations, detail = check_foreign_key(
        tmp_path,
        "sales_rep",
        "territory_id",
        "territory",
        "territory_id",
    )

    assert passed is False
    assert checked == 1
    assert violations == 1
    assert "missing references=1" in detail


def test_foreign_key_passes_for_existing_reference(tmp_path):
    write_csv(
        tmp_path / "sales_rep.csv",
        ["rep_id", "territory_id"],
        [{"rep_id": "R1", "territory_id": "T1"}],
    )
    write_csv(
        tmp_path / "territory.csv",
        ["territory_id"],
        [{"territory_id": "T1"}],
    )

    passed, checked, violations, _ = check_foreign_key(
        tmp_path,
        "sales_rep",
        "territory_id",
        "territory",
        "territory_id",
    )

    assert passed is True
    assert checked == 1
    assert violations == 0