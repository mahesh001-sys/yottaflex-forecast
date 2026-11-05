import argparse
import csv
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

TABLE_COLUMNS = {
    "territory": {
        "territory_id": "TEXT",
        "territory_name": "TEXT",
        "region": "TEXT",
        "country_code": "TEXT",
        "created_at": "TEXT",
        "status": "TEXT",
    },
    "stage": {
        "stage_id": "TEXT",
        "stage_name": "TEXT",
        "stage_order": "INTEGER",
        "default_probability": "REAL",
        "is_closed_stage": "INTEGER",
    },
    "sales_rep": {
        "rep_id": "TEXT",
        "rep_name": "TEXT",
        "email": "TEXT",
        "hire_date": "TEXT",
        "employment_status": "TEXT",
        "created_at": "TEXT",
    },
    "account": {
        "account_id": "TEXT",
        "account_name": "TEXT",
        "industry": "TEXT",
        "account_status": "TEXT",
        "territory_id": "TEXT",
        "created_at": "TEXT",
    },
    "rep_territory_assignment": {
        "assignment_id": "TEXT",
        "rep_id": "TEXT",
        "territory_id": "TEXT",
        "effective_from": "TEXT",
        "effective_to": "TEXT",
    },
    "opportunity": {
        "opportunity_id": "TEXT",
        "opportunity_name": "TEXT",
        "account_id": "TEXT",
        "owner_rep_id": "TEXT",
        "territory_id": "TEXT",
        "source_opportunity_id": "TEXT",
        "created_date": "TEXT",
        "expected_close_date": "TEXT",
        "amount": "REAL",
        "currency_code": "TEXT",
        "product": "TEXT",
        "current_stage": "TEXT",
        "closed_date": "TEXT",
        "outcome": "TEXT",
    },
    "stage_history": {
        "stage_history_id": "TEXT",
        "opportunity_id": "TEXT",
        "from_stage_id": "TEXT",
        "to_stage_id": "TEXT",
        "changed_by_rep_id": "TEXT",
        "changed_at": "TEXT",
        "reason": "TEXT",
        "event_sequence": "INTEGER",
    },
    "activity": {
        "activity_id": "TEXT",
        "opportunity_id": "TEXT",
        "rep_id": "TEXT",
        "activity_type": "TEXT",
        "activity_date": "TEXT",
        "subject": "TEXT",
        "outcome": "TEXT",
    },
    "quota": {
        "quota_id": "TEXT",
        "rep_id": "TEXT",
        "fiscal_quarter": "TEXT",
        "quota_amount": "REAL",
        "currency_code": "TEXT",
    },
    "historical_booking": {
        "booking_id": "TEXT",
        "opportunity_id": "TEXT",
        "account_id": "TEXT",
        "rep_id": "TEXT",
        "booking_date": "TEXT",
        "booking_amount": "REAL",
        "currency_code": "TEXT",
    },
    "forecast_snapshot": {
        "forecast_snapshot_id": "TEXT",
        "snapshot_date": "TEXT",
        "opportunity_id": "TEXT",
        "stage_id": "TEXT",
        "amount": "REAL",
        "expected_close_date": "TEXT",
        "last_activity_date": "TEXT",
        "stale_days": "INTEGER",
        "is_stale": "INTEGER",
    },
}

PRIMARY_KEYS = {
    "territory": "territory_id",
    "stage": "stage_id",
    "sales_rep": "rep_id",
    "account": "account_id",
    "rep_territory_assignment": "assignment_id",
    "opportunity": "opportunity_id",
    "stage_history": "stage_history_id",
    "activity": "activity_id",
    "quota": "quota_id",
    "historical_booking": "booking_id",
    "forecast_snapshot": "forecast_snapshot_id",
}

FOREIGN_KEYS = [
    ("account", "territory_id", "territory", "territory_id"),
    ("rep_territory_assignment", "rep_id", "sales_rep", "rep_id"),
    ("rep_territory_assignment", "territory_id", "territory", "territory_id"),
    ("opportunity", "account_id", "account", "account_id"),
    ("opportunity", "owner_rep_id", "sales_rep", "rep_id"),
    ("opportunity", "territory_id", "territory", "territory_id"),
    ("opportunity", "source_opportunity_id", "opportunity", "opportunity_id"),
    ("opportunity", "current_stage", "stage", "stage_name"),
    ("stage_history", "opportunity_id", "opportunity", "opportunity_id"),
    ("stage_history", "from_stage_id", "stage", "stage_id"),
    ("stage_history", "to_stage_id", "stage", "stage_id"),
    ("stage_history", "changed_by_rep_id", "sales_rep", "rep_id"),
    ("activity", "opportunity_id", "opportunity", "opportunity_id"),
    ("activity", "rep_id", "sales_rep", "rep_id"),
    ("quota", "rep_id", "sales_rep", "rep_id"),
    ("historical_booking", "opportunity_id", "opportunity", "opportunity_id"),
    ("historical_booking", "account_id", "account", "account_id"),
    ("historical_booking", "rep_id", "sales_rep", "rep_id"),
    ("forecast_snapshot", "opportunity_id", "opportunity", "opportunity_id"),
    ("forecast_snapshot", "stage_id", "stage", "stage_id"),
]

LOAD_ORDER = [
    "territory",
    "stage",
    "sales_rep",
    "account",
    "rep_territory_assignment",
    "opportunity",
    "stage_history",
    "activity",
    "quota",
    "historical_booking",
    "forecast_snapshot",
]

BOOLEAN_COLUMNS = {"is_closed_stage", "is_stale"}


def convert_value(column, value):
    """Convert CSV strings to appropriate SQLite values."""
    if value is None or value.strip() == "":
        return None

    value = value.strip()

    if column in BOOLEAN_COLUMNS:
        normalized = value.lower()
        if normalized in {"true", "1", "yes"}:
            return 1
        if normalized in {"false", "0", "no"}:
            return 0
        raise ValueError(f"Invalid boolean value for {column}: {value}")

    return value


def create_schema(connection):
    for table in LOAD_ORDER:
        columns = TABLE_COLUMNS[table]
        definitions = []

        for column, data_type in columns.items():
            definition = f'"{column}" {data_type}'

            if PRIMARY_KEYS[table] == column:
                definition += " PRIMARY KEY NOT NULL"

            if table == "stage" and column == "stage_name":
                definition += " UNIQUE"

            definitions.append(definition)

        for child, child_col, parent, parent_col in FOREIGN_KEYS:
            if child == table:
                definitions.append(
                    f'FOREIGN KEY ("{child_col}") '
                    f'REFERENCES "{parent}" ("{parent_col}")'
                )

        sql = (
            f'CREATE TABLE IF NOT EXISTS "{table}" '
            f"({', '.join(definitions)})"
        )
        connection.execute(sql)

    for child, child_col, _, _ in FOREIGN_KEYS:
        index_name = f"idx_{child}_{child_col}"
        connection.execute(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{child}" ("{child_col}")'
        )


def load_table(connection, data_dir, table):
    csv_path = data_dir / f"{table}.csv"

    if not csv_path.is_file():
        raise FileNotFoundError(f"Required CSV file not found: {csv_path}")

    columns = list(TABLE_COLUMNS[table])

    placeholders = ", ".join("?" for _ in columns)
    column_names = ", ".join(f'"{column}"' for column in columns)

    insert_sql = (
        f'INSERT INTO "{table}" ({column_names}) '
        f"VALUES ({placeholders})"
    )

    row_count = 0
    batch = []

    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != columns:
            raise ValueError(
                f"Unexpected CSV headers in {csv_path.name}.\n"
                f"Expected: {columns}\n"
                f"Found:    {reader.fieldnames}"
            )

        for row in reader:
            values = tuple(
                convert_value(column, row.get(column))
                for column in columns
            )
            batch.append(values)

            if len(batch) >= 5000:
                connection.executemany(insert_sql, batch)
                row_count += len(batch)
                batch.clear()

        if batch:
            connection.executemany(insert_sql, batch)
            row_count += len(batch)

    return row_count


def write_seed_sql(connection, output_path):
    """Write a complete SQL dump that can recreate the database."""
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        # The SQLite iterdump output creates and populates tables
        # alphabetically. Some child tables therefore appear before
        # their parent tables. Disable FK enforcement during import.
        file.write("PRAGMA foreign_keys = OFF;\n\n")

        for statement in connection.iterdump():
            file.write(statement)
            file.write("\n")

        # The dump ends with COMMIT. Re-enable FK enforcement afterward.
        file.write("\nPRAGMA foreign_keys = ON;\n")


def build_database(data_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)

    database_path = output_dir / "yottaflex.db"
    seed_path = output_dir / "seed.sql"

    if database_path.exists():
        database_path.unlink()

    connection = sqlite3.connect(database_path)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        create_schema(connection)

        print("\nLoading CSV data into SQLite")
        print("-" * 55)

        total_rows = 0

        for table in LOAD_ORDER:
            count = load_table(connection, data_dir, table)
            total_rows += count
            print(f"{table:<30} {count:>10,} rows")

        violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if violations:
            raise sqlite3.IntegrityError(
                f"Foreign-key violations detected: {violations[:10]}"
            )

        connection.commit()

        write_seed_sql(connection, seed_path)

        print("-" * 55)
        print(f"{'TOTAL':<30} {total_rows:>10,} rows")
        print("\nDatabase build successful.")
        print(f"SQLite database: {database_path}")
        print(f"SQL seed file:   {seed_path}")
        print("Foreign-key check: PASS (0 violations)")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Build the YottaFlex SQLite database from CSV files."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
        help="Directory containing source CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
        help="Directory for the SQLite database and SQL seed file.",
    )

    args = parser.parse_args()

    try:
        build_database(args.data_dir, args.output_dir)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())