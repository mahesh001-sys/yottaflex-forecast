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

# The 15 relationships selected for this checker.
FOREIGN_KEYS = [
    ("sales_rep", "territory_id", "territory", "territory_id"),
    ("rep_territory_assignment", "rep_id", "sales_rep", "rep_id"),
    ("rep_territory_assignment", "territory_id", "territory", "territory_id"),
    ("account", "account_id", "opportunity", "account_id"),
    ("opportunity", "owner_rep_id", "sales_rep", "rep_id"),
    ("opportunity", "stage_id", "stage", "stage_id"),
    ("stage_history", "opportunity_id", "opportunity", "opportunity_id"),
    ("stage_history", "to_stage_id", "stage", "stage_id"),
    ("activity", "opportunity_id", "opportunity", "opportunity_id"),
    ("activity", "rep_id", "sales_rep", "rep_id"),
    ("quota", "rep_id", "sales_rep", "rep_id"),
    ("quota", "territory_id", "territory", "territory_id"),
    ("historical_booking", "opportunity_id", "opportunity", "opportunity_id"),
    ("forecast_snapshot", "stage_id", "stage", "stage_id"),
    ("forecast_snapshot", "opportunity_id", "opportunity", "opportunity_id"),
]


def read_csv(data_dir, table_name):
    path = data_dir / f"{table_name}.csv"
    if not path.exists():
        return None

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def check_primary_key(data_dir, table_name, key):
    rows = read_csv(data_dir, table_name)

    if rows is None:
        return False, 0, 1, f"missing file: {table_name}.csv"

    blank_count = sum(not (row.get(key) or "").strip() for row in rows)
    values = [
        (row.get(key) or "").strip()
        for row in rows
        if (row.get(key) or "").strip()
    ]
    duplicate_count = sum(count - 1 for count in Counter(values).values() if count > 1)
    violations = blank_count + duplicate_count

    return (
        violations == 0,
        len(rows),
        violations,
        f"blank={blank_count}, duplicates={duplicate_count}",
    )


def check_foreign_key(data_dir, child_table, child_column, parent_table, parent_column):
    child_rows = read_csv(data_dir, child_table)
    parent_rows = read_csv(data_dir, parent_table)

    if child_rows is None:
        return False, 0, 1, f"missing child file: {child_table}.csv"

    if parent_rows is None:
        return False, len(child_rows), 1, f"missing parent file: {parent_table}.csv"

    parent_values = {
        (row.get(parent_column) or "").strip()
        for row in parent_rows
        if (row.get(parent_column) or "").strip()
    }

    checked = 0
    violations = 0

    for row in child_rows:
        value = (row.get(child_column) or "").strip()

        # Empty foreign-key values are treated as optional.
        if not value:
            continue

        checked += 1
        if value not in parent_values:
            violations += 1

    return (
        violations == 0,
        checked,
        violations,
        f"missing references={violations}",
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
            data_dir, table_name, key
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