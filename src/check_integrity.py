import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


# Core tables and their primary keys.
PRIMARY_KEYS = {
    "territory": "territory_id",
    "sales_rep": "rep_id",
    "rep_territory_assignment": "assignment_id",
    "account": "account_id",
    "opportunity": "opportunity_id",
    "stage": "stage_id",
    "stage_history": "stage_history_id",
    "activity": "activity_id",
    "quota": "quota_id",
    "historical_booking": "booking_id",
    "forecast_snapshot": "forecast_snapshot_id",
}


# Foreign-key relationships matching src/database.py.
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


# Only these foreign-key columns are allowed to contain blank values.
OPTIONAL_FOREIGN_KEYS = {
    ("opportunity", "source_opportunity_id"),
    ("stage_history", "from_stage_id"),
}


def read_csv(data_dir, table_name):
    """Read a CSV and return its column names and rows."""
    path = data_dir / f"{table_name}.csv"

    if not path.exists():
        return None

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        rows = list(reader)

    return columns, rows


def check_primary_key(data_dir, table_name, key):
    """Check primary-key column existence, blanks, and duplicates."""
    result = read_csv(data_dir, table_name)

    if result is None:
        return False, 0, 1, f"missing file: {table_name}.csv"

    columns, rows = result

    if key not in columns:
        return (
            False,
            len(rows),
            1,
            f"missing primary-key column: {key}",
        )

    blank_count = sum(
        not (row.get(key) or "").strip()
        for row in rows
    )

    values = [
        (row.get(key) or "").strip()
        for row in rows
        if (row.get(key) or "").strip()
    ]

    duplicate_count = sum(
        count - 1
        for count in Counter(values).values()
        if count > 1
    )

    violations = blank_count + duplicate_count

    return (
        violations == 0,
        len(rows),
        violations,
        f"blank={blank_count}, duplicates={duplicate_count}",
    )


def check_foreign_key(
    data_dir,
    child_table,
    child_column,
    parent_table,
    parent_column,
):
    """Check foreign-key column existence and parent references."""
    child_result = read_csv(data_dir, child_table)
    parent_result = read_csv(data_dir, parent_table)

    if child_result is None:
        return (
            False,
            0,
            1,
            f"missing child file: {child_table}.csv",
        )

    if parent_result is None:
        return (
            False,
            0,
            1,
            f"missing parent file: {parent_table}.csv",
        )

    child_columns, child_rows = child_result
    parent_columns, parent_rows = parent_result

    if child_column not in child_columns:
        return (
            False,
            len(child_rows),
            1,
            f"missing child column: {child_column}",
        )

    if parent_column not in parent_columns:
        return (
            False,
            len(child_rows),
            1,
            f"missing parent column: {parent_column}",
        )

    parent_values = {
        (row.get(parent_column) or "").strip()
        for row in parent_rows
        if (row.get(parent_column) or "").strip()
    }

    optional = (child_table, child_column) in OPTIONAL_FOREIGN_KEYS

    checked = 0
    violations = 0
    blank_count = 0

    for row in child_rows:
        value = (row.get(child_column) or "").strip()

        if not value:
            blank_count += 1

            if not optional:
                violations += 1

            continue

        checked += 1

        if value not in parent_values:
            violations += 1

    return (
        violations == 0,
        checked,
        violations,
        (
            f"missing references={violations - (blank_count if not optional else 0)}, "
            f"blank={blank_count}, optional={optional}"
        ),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Check primary-key uniqueness and foreign-key integrity."
    )

    parser.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="Directory containing the raw CSV tables.",
    )

    args = parser.parse_args()
    data_dir = args.data_dir

    if not data_dir.is_dir():
        print(f"ERROR | data directory does not exist: {data_dir}")
        return 2

    total_checks = 0
    total_failures = 0

    for table_name, key in PRIMARY_KEYS.items():
        passed, checked, violations, detail = check_primary_key(
            data_dir,
            table_name,
            key,
        )

        total_checks += 1
        total_failures += int(not passed)

        print(
            f"{'PASS' if passed else 'FAIL'} | "
            f"{table_name} primary-key uniqueness | "
            f"rows={checked}, violations={violations} | {detail}"
        )

    for child_table, child_column, parent_table, parent_column in FOREIGN_KEYS:
        passed, checked, violations, detail = check_foreign_key(
            data_dir,
            child_table,
            child_column,
            parent_table,
            parent_column,
        )

        total_checks += 1
        total_failures += int(not passed)

        print(
            f"{'PASS' if passed else 'FAIL'} | "
            f"{child_table}.{child_column} -> "
            f"{parent_table}.{parent_column} | "
            f"checked={checked}, violations={violations} | {detail}"
        )

    print(
        f"\nIntegrity checks: {total_checks} | "
        f"failed checks: {total_failures}"
    )

    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())