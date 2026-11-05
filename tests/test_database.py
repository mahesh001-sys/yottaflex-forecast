
import csv
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.database import LOAD_ORDER, PRIMARY_KEYS, build_database
from src.export_json import export_all


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "yottaflex.db"
JSON_DIR = PROCESSED_DIR / "json"


@pytest.fixture
def database():
    # Make the suite self-contained on a clean clone. Generated artifacts are
    # reproducible from the committed CSV source data and must not be required
    # to exist before pytest starts.
    if not DB_PATH.exists():
        build_database(RAW_DIR, PROCESSED_DIR)
    if not all((JSON_DIR / f"{table}.json").exists() for table in LOAD_ORDER):
        export_all(DB_PATH, JSON_DIR)

    connection = sqlite3.connect(DB_PATH)
    yield connection
    connection.close()


def test_csv_sqlite_json_row_counts_match(database):
    for table in LOAD_ORDER:
        with (RAW_DIR / f"{table}.csv").open(
            encoding="utf-8-sig", newline=""
        ) as file:
            csv_count = sum(1 for _ in csv.DictReader(file))

        sqlite_count = database.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]

        with (JSON_DIR / f"{table}.json").open(
            encoding="utf-8"
        ) as file:
            json_count = len(json.load(file))

        assert csv_count == sqlite_count == json_count, (
            f"{table}: CSV={csv_count}, "
            f"SQLite={sqlite_count}, JSON={json_count}"
        )


def test_foreign_key_integrity(database):
    database.execute("PRAGMA foreign_keys = ON")
    violations = database.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    assert violations == []


def test_sql_weighted_pipeline_matches_pandas(database):
    sql_rows = database.execute(
        """
        SELECT
            o.territory_id,
            SUM(fs.amount * s.default_probability)
        FROM forecast_snapshot fs
        JOIN opportunity o
            ON fs.opportunity_id = o.opportunity_id
        JOIN stage s
            ON fs.stage_id = s.stage_id
        GROUP BY o.territory_id
        """
    ).fetchall()

    sql_totals = {
        territory: round(total, 2)
        for territory, total in sql_rows
    }

    snapshots = pd.read_csv(RAW_DIR / "forecast_snapshot.csv")
    opportunities = pd.read_csv(
        RAW_DIR / "opportunity.csv",
        usecols=["opportunity_id", "territory_id"],
    )
    stages = pd.read_csv(
        RAW_DIR / "stage.csv",
        usecols=["stage_id", "default_probability"],
    )

    frame = snapshots.merge(
        opportunities,
        on="opportunity_id",
        validate="many_to_one",
    ).merge(
        stages,
        on="stage_id",
        validate="many_to_one",
    )

    frame["amount"] = pd.to_numeric(frame["amount"])
    frame["default_probability"] = pd.to_numeric(
        frame["default_probability"]
    )
    frame["expected_revenue"] = (
        frame["amount"] * frame["default_probability"]
    )

    pandas_totals = (
        frame.groupby("territory_id")["expected_revenue"]
        .sum()
        .round(2)
        .to_dict()
    )

    assert sql_totals.keys() == pandas_totals.keys()

    for territory in sql_totals:
        assert sql_totals[territory] == pytest.approx(
            pandas_totals[territory],
            abs=0.02,
        )


def test_database_primary_keys_and_foreign_keys(database):
    for table, primary_key in PRIMARY_KEYS.items():
        columns = database.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()

        primary_key_columns = {
            row[1] for row in columns if row[5] > 0
        }

        assert primary_key in primary_key_columns, (
            f"{table} is missing primary key {primary_key}"
        )

        foreign_keys = database.execute(
            f'PRAGMA foreign_key_list("{table}")'
        ).fetchall()

        assert isinstance(foreign_keys, list)



def test_json_export_round_trip_matches_sqlite_sample_rows(database):
    for table in LOAD_ORDER:
        primary_key = PRIMARY_KEYS[table]
        with (JSON_DIR / f"{table}.json").open(encoding="utf-8") as file:
            json_rows = json.load(file)

        cursor = database.execute(
            f'SELECT * FROM "{table}" ORDER BY "{primary_key}" LIMIT 1'
        )
        columns = [item[0] for item in cursor.description]
        sqlite_row = dict(zip(columns, cursor.fetchone()))

        assert json_rows[0] == sqlite_row, table

        with (RAW_DIR / f"{table}.csv").open(
            encoding="utf-8-sig", newline=""
        ) as file:
            csv_rows = csv.DictReader(file)
            matching_csv_row = next(
                (
                    row for row in csv_rows
                    if row[primary_key] == json_rows[0][primary_key]
                ),
                None,
            )

        assert matching_csv_row is not None, table
