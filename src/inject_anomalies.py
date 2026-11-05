"""Copy clean data and inject five labelled anomalies.

Run from the repository root:
    python -m src.inject_anomalies

The source data/raw directory is never modified.
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import date, timedelta
from pathlib import Path


RAW_DIR = Path("data/raw")
ANOMALY_DIR = Path("data/anomalies")

GROUND_TRUTH_FIELDS = ["issue_type", "table", "record_id", "description"]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def require_columns(path: Path, fields: list[str], required: set[str]) -> None:
    missing = required.difference(fields)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")


def create_anomaly_fixtures(
    raw_dir: Path = RAW_DIR,
    anomaly_dir: Path = ANOMALY_DIR,
) -> list[dict[str, str]]:
    """Copy raw data and inject exactly five anomalies into the copy."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Missing clean data directory: {raw_dir}")

    if anomaly_dir.exists():
        shutil.rmtree(anomaly_dir)
    shutil.copytree(raw_dir, anomaly_dir)

    opportunity_path = anomaly_dir / "opportunity.csv"
    snapshot_path = anomaly_dir / "forecast_snapshot.csv"
    stage_path = anomaly_dir / "stage.csv"
    history_path = anomaly_dir / "stage_history.csv"

    opp_fields, opportunities = read_csv(opportunity_path)
    snap_fields, snapshots = read_csv(snapshot_path)
    stage_fields, stages = read_csv(stage_path)
    hist_fields, history = read_csv(history_path)

    require_columns(
        opportunity_path,
        opp_fields,
        {"opportunity_id", "created_date", "closed_date", "outcome", "currency_code"},
    )
    require_columns(
        snapshot_path,
        snap_fields,
        {"forecast_snapshot_id", "snapshot_date", "opportunity_id", "stage_id"},
    )
    require_columns(
        stage_path,
        stage_fields,
        {"stage_id", "stage_name", "stage_order", "default_probability"},
    )
    require_columns(
        history_path,
        hist_fields,
        {"opportunity_id", "to_stage_id", "changed_at"},
    )

    truth: list[dict[str, str]] = []
    used_opportunity_ids: set[str] = set()
    used_snapshot_ids: set[str] = set()

    def add_truth(issue_type: str, table: str, record_id: str, description: str) -> None:
        truth.append({
            "issue_type": issue_type,
            "table": table,
            "record_id": record_id,
            "description": description,
        })

    # 1. Close date before creation date.
    close_row = next(
        (
            row for row in opportunities
            if row.get("opportunity_id")
            and row["opportunity_id"] not in used_opportunity_ids
            and row.get("outcome", "").lower() in {"won", "lost"}
            and parse_date(row.get("created_date", "")) is not None
        ),
        None,
    )
    if close_row is None:
        raise ValueError("No closed opportunity is available for the close-date anomaly.")

    close_id = close_row["opportunity_id"]
    created = parse_date(close_row["created_date"])
    assert created is not None
    close_row["closed_date"] = (created - timedelta(days=1)).isoformat()
    used_opportunity_ids.add(close_id)
    add_truth(
        "close_date_before_creation",
        "opportunity",
        close_id,
        "closed_date is one day before created_date.",
    )

    # 2. EUR in a USD dataset.
    currency_row = next(
        (
            row for row in opportunities
            if row.get("opportunity_id")
            and row["opportunity_id"] not in used_opportunity_ids
            and row.get("currency_code", "").upper() == "USD"
        ),
        None,
    )
    if currency_row is None:
        raise ValueError("No unused USD opportunity is available for the currency anomaly.")

    currency_id = currency_row["opportunity_id"]
    currency_row["currency_code"] = "EUR"
    used_opportunity_ids.add(currency_id)
    add_truth(
        "mixed_currency",
        "opportunity",
        currency_id,
        "currency_code is EUR in a USD dataset.",
    )

    stage_by_id = {row["stage_id"]: row for row in stages}
    stage_order = {
        stage_id: int(row["stage_order"])
        for stage_id, row in stage_by_id.items()
    }

    history_by_opportunity: dict[str, list[dict[str, str]]] = {}
    for row in history:
        history_by_opportunity.setdefault(row.get("opportunity_id", ""), []).append(row)

    def latest_history_stage(opportunity_id: str) -> str | None:
        dated_events = []
        for event in history_by_opportunity.get(opportunity_id, []):
            when = parse_date(event.get("changed_at", ""))
            stage_id = event.get("to_stage_id", "")
            if when is not None and stage_id:
                dated_events.append((when, stage_id))
        return max(dated_events, key=lambda item: item[0])[1] if dated_events else None

    # 3. Probability inconsistent with the snapshot stage.
    probability_row = next(
        (
            row for row in snapshots
            if row.get("forecast_snapshot_id")
            and row["forecast_snapshot_id"] not in used_snapshot_ids
            and row.get("stage_id") in stage_by_id
            and row.get("opportunity_id") not in used_opportunity_ids
        ),
        None,
    )
    if probability_row is None:
        raise ValueError("No snapshot is available for the probability anomaly.")

    probability_id = probability_row["forecast_snapshot_id"]
    expected_probability = float(
        stage_by_id[probability_row["stage_id"]]["default_probability"]
    )
    injected_probability = 0.123456
    if abs(injected_probability - expected_probability) < 1e-9:
        injected_probability = 0.876543

    if "stage_probability" not in snap_fields:
        snap_fields.append("stage_probability")
    probability_row["stage_probability"] = str(injected_probability)
    used_snapshot_ids.add(probability_id)
    add_truth(
        "stage_probability_mismatch",
        "forecast_snapshot",
        probability_id,
        "stage_probability differs from the default probability for stage_id.",
    )

    # 4. Snapshot stage replaced with a stage reached after snapshot_date.
    leak_row = None
    for row in snapshots:
        if (
            not row.get("forecast_snapshot_id")
            or row["forecast_snapshot_id"] in used_snapshot_ids
            or row.get("opportunity_id") in used_opportunity_ids
        ):
            continue

        snapshot_day = parse_date(row.get("snapshot_date", ""))
        current_stage = row.get("stage_id", "")
        if snapshot_day is None or current_stage not in stage_order:
            continue

        future_events = []
        for event in history_by_opportunity.get(row["opportunity_id"], []):
            event_day = parse_date(event.get("changed_at", ""))
            future_stage = event.get("to_stage_id", "")
            if event_day and event_day > snapshot_day and future_stage in stage_order:
                future_events.append((event_day, future_stage))

        if future_events:
            later_stage = max(
                future_events,
                key=lambda item: (item[0], stage_order[item[1]]),
            )[1]
            if stage_order[later_stage] > stage_order[current_stage]:
                leak_row = row
                break

    if leak_row is None:
        raise ValueError("No snapshot is available for the future-information anomaly.")

    leak_id = leak_row["forecast_snapshot_id"]
    leak_row["stage_id"] = latest_history_stage(leak_row["opportunity_id"]) or leak_row["stage_id"]
    used_snapshot_ids.add(leak_id)
    add_truth(
        "future_information_leak",
        "forecast_snapshot",
        leak_id,
        "Snapshot stage was replaced with a later stage from the opportunity's history.",
    )

    # 5. Duplicate an opportunity on the same snapshot date.
    duplicate_source = next(
        (
            row for row in snapshots
            if row.get("forecast_snapshot_id")
            and row["forecast_snapshot_id"] not in used_snapshot_ids
            and row.get("opportunity_id") not in used_opportunity_ids
        ),
        None,
    )
    if duplicate_source is None:
        raise ValueError("No snapshot is available for the duplicate-opportunity anomaly.")

    duplicate = dict(duplicate_source)
    duplicate_id = duplicate["forecast_snapshot_id"] + "-ANOM"
    duplicate["forecast_snapshot_id"] = duplicate_id
    snapshots.append(duplicate)
    add_truth(
        "duplicate_opportunity",
        "forecast_snapshot",
        duplicate_id,
        "A second row repeats the same opportunity_id on the same snapshot_date.",
    )

    write_csv(opportunity_path, opp_fields, opportunities)
    write_csv(snapshot_path, snap_fields, snapshots)

    with (anomaly_dir / "ground_truth.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=GROUND_TRUTH_FIELDS)
        writer.writeheader()
        writer.writerows(truth)

    with (anomaly_dir / "ground_truth.json").open("w", encoding="utf-8") as file:
        json.dump(truth, file, indent=2)
        file.write("\n")

    return truth


def main() -> int:
    truth = create_anomaly_fixtures()
    print(f"Injected {len(truth)} labelled anomalies into {ANOMALY_DIR}:")
    for item in truth:
        print(f"  {item['issue_type']} | {item['table']} | {item['record_id']}")
    print("The source data/raw directory was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())