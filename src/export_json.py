
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from src.database import LOAD_ORDER, PRIMARY_KEYS


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def export_table(connection, table, output_dir):
    """Export one SQLite table as a JSON array."""
    output_path = output_dir / f"{table}.json"
    primary_key = PRIMARY_KEYS[table]

    cursor = connection.execute(
        f'SELECT * FROM "{table}" ORDER BY "{primary_key}"'
    )

    column_names = [description[0] for description in cursor.description]
    row_count = 0

    # Stream records to avoid holding large tables in memory.
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write("[\n")

        first_record = True

        for row in cursor:
            record = dict(zip(column_names, row))

            if not first_record:
                file.write(",\n")

            json.dump(
                record,
                file,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            first_record = False
            row_count += 1

        file.write("\n]\n")

    return row_count, output_path


def export_all(db_path, output_dir):
    if not db_path.is_file():
        raise FileNotFoundError(
            f"SQLite database not found: {db_path}. "
            "Run python -m src.database first."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)

    try:
        print("\nExporting SQLite tables to JSON")
        print("-" * 55)

        total_rows = 0

        for table in LOAD_ORDER:
            count, output_path = export_table(
                connection,
                table,
                output_dir,
            )

            total_rows += count

            print(
                f"{table:<30} {count:>10,} rows | "
                f"{output_path.name}"
            )

        print("-" * 55)
        print(f"{'TOTAL':<30} {total_rows:>10,} rows")
        print(f"\nJSON export successful: {output_dir}")

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Export all YottaFlex SQLite tables to JSON."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "yottaflex.db",
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "json",
        help="Directory for exported JSON files.",
    )

    args = parser.parse_args()

    try:
        export_all(args.db_path, args.output_dir)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
