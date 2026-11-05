import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


ALLOWED_ENUMS = {
    ("account", "account_status"): {"Customer", "Prospect", "Disqualified"},
    ("sales_rep", "employment_status"): {"Active", "Inactive"},
    ("territory", "status"): {"Active", "Inactive"},
    ("opportunity", "current_stage"): {
        "Prospecting",
        "Qualification",
        "Proposal",
        "Negotiation",
        "Closed Won",
        "Closed Lost",
    },
    ("opportunity", "outcome"): {"Open", "Won", "Lost"},
    ("activity", "activity_type"): {"Call", "Email", "Meeting"},
}

VALID_TRANSITIONS = {
    "Prospecting": {"Qualification", "Closed Lost"},
    "Qualification": {"Proposal", "Closed Lost"},
    "Proposal": {"Negotiation", "Closed Lost"},
    "Negotiation": {"Closed Won", "Closed Lost"},
    "Closed Won": set(),
    "Closed Lost": set(),
}


def read_csv(path):
    if not path.exists():
        return None

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_datetime(value):
    value = (value or "").strip()
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = parse_date(value)
        return datetime.combine(parsed, datetime.min.time()) if parsed else None


def parse_number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def emit(name, checked, violations, detail=""):
    passed = violations == 0
    print(
        f"{'PASS' if passed else 'FAIL'} | {name} | "
        f"checked={checked}, violations={violations}"
        + (f" | {detail}" if detail else "")
    )
    return violations


def check_enums(data_dir):
    checked = 0
    violations = 0

    for (table, column), allowed in ALLOWED_ENUMS.items():
        rows = read_csv(data_dir / f"{table}.csv")

        if rows is None:
            violations += 1
            print(f"FAIL | enum {table}.{column} | missing file")
            continue

        if rows and column not in rows[0]:
            violations += 1
            print(f"FAIL | enum {table}.{column} | missing column")
            continue

        for row in rows:
            value = (row.get(column) or "").strip()
            checked += 1

            if value not in allowed:
                violations += 1

    return emit("allowed enums", checked, violations)


def check_date_ordering(data_dir):
    rows = read_csv(data_dir / "opportunity.csv")

    if rows is None:
        return emit("date ordering", 0, 1, "missing opportunity.csv")

    checked = 0
    violations = 0

    for row in rows:
        created = parse_date(row.get("created_date"))
        close = parse_date(row.get("expected_close_date"))
        checked += 1

        if created is None or close is None or close < created:
            violations += 1

    return emit("date ordering", checked, violations)


def check_lifecycle(data_dir):
    history = read_csv(data_dir / "stage_history.csv")
    stages = read_csv(data_dir / "stage.csv")

    if history is None or stages is None:
        return emit("StageHistory lifecycle", 0, 1, "missing required file")

    stage_names = {
        (row.get("stage_id") or "").strip():
        (row.get("stage_name") or "").strip()
        for row in stages
    }

    by_opportunity = defaultdict(list)
    violations = 0

    for row in history:
        opportunity_id = (row.get("opportunity_id") or "").strip()
        changed_at = parse_datetime(row.get("changed_at"))
        from_id = (row.get("from_stage_id") or "").strip()
        to_id = (row.get("to_stage_id") or "").strip()

        if not opportunity_id or changed_at is None or to_id not in stage_names:
            violations += 1
            continue

        by_opportunity[opportunity_id].append(
            (changed_at, stage_names.get(from_id, ""), stage_names[to_id])
        )

    checked = len(history)

    for events in by_opportunity.values():
        events.sort(key=lambda event: event[0])
        previous_stage = None

        for _, from_stage, to_stage in events:
            if previous_stage is None:
                if from_stage and from_stage != to_stage:
                    violations += 1

                if to_stage != "Prospecting" and from_stage == "":
                    violations += 1
            else:
                if from_stage != previous_stage:
                    violations += 1

                if to_stage not in VALID_TRANSITIONS.get(previous_stage, set()):
                    violations += 1

            previous_stage = to_stage

    return emit("StageHistory lifecycle", checked, violations)


def check_weighted_pipeline(data_dir):
    processed_dir = data_dir.parent / "processed"
    detail = read_csv(processed_dir / "forecast_detail.csv")
    summary = read_csv(processed_dir / "forecast_summary.csv")

    if detail is None or summary is None:
        return emit(
            "weighted pipeline reconciliation",
            0,
            1,
            "missing processed forecast_detail.csv or forecast_summary.csv",
        )

    checked = 0
    violations = 0
    calculated_totals = defaultdict(float)
    summary_totals = {}

    for row in detail:
        amount = parse_number(row.get("amount"))
        probability = parse_number(row.get("stage_probability"))
        expected_revenue = parse_number(row.get("expected_revenue"))
        checked += 1

        if amount is None or probability is None or expected_revenue is None:
            violations += 1
            continue

        calculated = amount * probability

        if abs(calculated - expected_revenue) > 0.02:
            violations += 1

        key = (
            (row.get("quarter") or "").strip(),
            (row.get("territory_id") or "").strip(),
            (row.get("stage_id") or "").strip(),
        )
        calculated_totals[key] += expected_revenue

    for row in summary:
        key = (
            (row.get("quarter") or "").strip(),
            (row.get("territory_id") or "").strip(),
            (row.get("stage_id") or "").strip(),
        )
        value = parse_number(row.get("total_weighted_pipeline"))

        if value is None or key in summary_totals:
            violations += 1
            continue

        summary_totals[key] = value

    all_keys = set(calculated_totals) | set(summary_totals)

    for key in all_keys:
        if key not in calculated_totals or key not in summary_totals:
            violations += 1
            continue

        if abs(calculated_totals[key] - summary_totals[key]) > 0.02:
            violations += 1

    return emit(
        "weighted pipeline reconciliation",
        checked,
        violations,
        f"detail groups={len(calculated_totals)}, "
        f"summary groups={len(summary_totals)}",
    )


def check_snapshot_time_consistency(data_dir):
    snapshots = read_csv(data_dir / "forecast_snapshot.csv")
    history = read_csv(data_dir / "stage_history.csv")

    if snapshots is None or history is None:
        return emit(
            "snapshot time-consistency",
            0,
            1,
            "missing required file",
        )

    events_by_opportunity = defaultdict(list)

    for row in history:
        opportunity_id = (row.get("opportunity_id") or "").strip()
        changed_at = parse_datetime(row.get("changed_at"))
        stage_id = (row.get("to_stage_id") or "").strip()

        if opportunity_id and changed_at and stage_id:
            events_by_opportunity[opportunity_id].append((changed_at, stage_id))

    for events in events_by_opportunity.values():
        events.sort(key=lambda event: event[0])

    checked = 0
    violations = 0

    for row in snapshots:
        checked += 1
        snapshot_date = parse_date(row.get("snapshot_date"))
        last_activity_date = parse_date(row.get("last_activity_date"))

        if snapshot_date is None:
            violations += 1
            continue

        if last_activity_date and last_activity_date > snapshot_date:
            violations += 1

        opportunity_id = (row.get("opportunity_id") or "").strip()
        snapshot_stage_id = (row.get("stage_id") or "").strip()

        eligible_events = [
            event
            for event in events_by_opportunity.get(opportunity_id, [])
            if event[0].date() <= snapshot_date
        ]

        if eligible_events:
            latest_stage_id = eligible_events[-1][1]

            if snapshot_stage_id != latest_stage_id:
                violations += 1

    return emit("snapshot time-consistency", checked, violations)


def check_duplicate_snapshot_opportunities(data_dir):
    rows = read_csv(data_dir / "forecast_snapshot.csv")

    if rows is None:
        return emit(
            "no duplicate opportunity within snapshot",
            0,
            1,
            "missing forecast_snapshot.csv",
        )

    seen = set()
    violations = 0

    for row in rows:
        key = (
            (row.get("snapshot_date") or "").strip(),
            (row.get("opportunity_id") or "").strip(),
        )

        if key in seen:
            violations += 1

        seen.add(key)

    return emit(
        "no duplicate opportunity within snapshot",
        len(rows),
        violations,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Validate business rules in the forecast dataset."
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="Directory containing the raw CSV tables.",
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"ERROR | data directory does not exist: {args.data_dir}")
        return 2

    checks = [
        check_enums,
        check_date_ordering,
        check_lifecycle,
        check_weighted_pipeline,
        check_snapshot_time_consistency,
        check_duplicate_snapshot_opportunities,
    ]

    total_violations = 0

    for check in checks:
        total_violations += check(args.data_dir)

    print(
        f"\nBusiness-rule checks: {len(checks)} | "
        f"violations: {total_violations}"
    )
    return 1 if total_violations else 0


if __name__ == "__main__":
    sys.exit(main())