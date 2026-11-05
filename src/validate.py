"""Run dataset integrity and business-rule validation.

Examples:
    python -m src.validate --data-dir data/raw
    python -m src.validate --data-dir data/anomalies
"""
from __future__ import annotations

import argparse
import csv
import io
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from src import check_business_rules as business
from src import check_integrity as integrity


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV file, returning an empty list when it is absent."""
    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def parse_datetime(value: str) -> datetime | None:
    """Parse ISO dates and normalize timezone-aware values to naive UTC."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value[:10])
        except ValueError:
            return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def record_issue(
    issues: list[dict[str, str]],
    issue_type: str,
    table: str,
    record_id: str,
    description: str,
) -> None:
    """Append a normalized custom validation issue."""
    issues.append({
        "issue_type": issue_type,
        "table": table,
        "record_id": record_id,
        "description": description,
    })


def run_checks(data_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Run integrity, business, and custom checks without reading ground truth."""
    issues: list[dict[str, str]] = []
    summaries: list[str] = []

    # Existing primary-key checks.
    for table, key in integrity.PRIMARY_KEYS.items():
        passed, row_count, violations, detail = integrity.check_primary_key(
            data_dir, table, key
        )
        summaries.append(
            f"Primary key {table}.{key}: {'PASS' if passed else 'FAIL'} "
            f"({row_count} rows; {violations} violations) — {detail}"
        )

    # Existing foreign-key checks.
    for child_table, child_column, parent_table, parent_column in integrity.FOREIGN_KEYS:
        passed, row_count, violations, detail = integrity.check_foreign_key(
            data_dir,
            child_table,
            child_column,
            parent_table,
            parent_column,
        )
        summaries.append(
            f"Foreign key {child_table}.{child_column} -> "
            f"{parent_table}.{parent_column}: {'PASS' if passed else 'FAIL'} "
            f"({row_count} rows; {violations} violations) — {detail}"
        )

    # Existing business-rule checks.
    business_checks = [
        ("Enums", business.check_enums),
        ("Date ordering", business.check_date_ordering),
        ("Lifecycle", business.check_lifecycle),
        ("Weighted pipeline", business.check_weighted_pipeline),
        ("Snapshot time consistency", business.check_snapshot_time_consistency),
        (
            "Duplicate snapshot opportunities",
            business.check_duplicate_snapshot_opportunities,
        ),
    ]

    for label, check in business_checks:
        captured = io.StringIO()
        with redirect_stdout(captured):
            violations = check(data_dir)

        summaries.append(f"{label}: {violations} violation(s)")
        details = captured.getvalue().strip()
        if details:
            summaries.extend(details.splitlines())

    # Load tables for custom anomaly checks.
    opportunities = read_rows(data_dir / "opportunity.csv")
    snapshots = read_rows(data_dir / "forecast_snapshot.csv")
    stages = read_rows(data_dir / "stage.csv")
    history = read_rows(data_dir / "stage_history.csv")

    # Group stage-history events by opportunity.
    history_by_opportunity: dict[str, list[dict[str, str]]] = defaultdict(list)
    for event in history:
        opportunity_id = event.get("opportunity_id", "")
        if opportunity_id:
            history_by_opportunity[opportunity_id].append(event)

    # Closed date must not precede creation date.
    for row in opportunities:
        created = parse_datetime(row.get("created_date", ""))
        closed = parse_datetime(row.get("closed_date", ""))

        if created and closed and closed < created:
            record_issue(
                issues,
                "close_date_before_creation",
                "opportunity",
                row.get("opportunity_id", ""),
                "closed_date is before created_date.",
            )

    # The dataset's expected currency is USD.
    for row in opportunities:
        currency = row.get("currency_code", "").strip().upper()

        if currency and currency != "USD":
            record_issue(
                issues,
                "mixed_currency",
                "opportunity",
                row.get("opportunity_id", ""),
                f"Unexpected currency_code: {currency}.",
            )

    # A provided snapshot probability must match its stage's default.
    probability_by_stage = {
        row.get("stage_id", ""): row.get("default_probability", "")
        for row in stages
    }

    for row in snapshots:
        observed = row.get("stage_probability", "").strip()
        expected = probability_by_stage.get(row.get("stage_id", ""), "").strip()

        if not observed or not expected:
            continue

        try:
            mismatch = abs(float(observed) - float(expected)) > 1e-9
        except ValueError:
            mismatch = True

        if mismatch:
            record_issue(
                issues,
                "stage_probability_mismatch",
                "forecast_snapshot",
                row.get("forecast_snapshot_id", ""),
                f"stage_probability {observed!r} does not match "
                f"stage default {expected!r}.",
            )

    # Flag a future-information leak only if the snapshot stage:
    # 1. appears in stage history after the snapshot date, and
    # 2. does not appear in any stage history on or before that date.
    #
    # A later stage progression alone is not a leak. A snapshot using
    # STAGE-001 is valid if STAGE-001 was already recorded by that date,
    # even if the opportunity advances to another stage later.
    for snapshot in snapshots:
        snapshot_date = parse_datetime(snapshot.get("snapshot_date", ""))
        opportunity_id = snapshot.get("opportunity_id", "")
        snapshot_stage = snapshot.get("stage_id", "")

        if not snapshot_date or not opportunity_id or not snapshot_stage:
            continue

        prior_stage_ids: set[str] = set()
        future_stage_ids: set[str] = set()

        for event in history_by_opportunity.get(opportunity_id, []):
            event_date = parse_datetime(event.get("changed_at", ""))
            event_stage = event.get("to_stage_id", "")

            if not event_date or not event_stage:
                continue

            if event_date.date() <= snapshot_date.date():
                prior_stage_ids.add(event_stage)
            else:
                future_stage_ids.add(event_stage)

        if (
            snapshot_stage in future_stage_ids
            and snapshot_stage not in prior_stage_ids
        ):
            record_issue(
                issues,
                "future_information_leak",
                "forecast_snapshot",
                snapshot.get("forecast_snapshot_id", ""),
                "Snapshot uses a stage recorded only after snapshot_date.",
            )

    # Detect duplicate opportunity entries within a snapshot date.
    seen: set[tuple[str, str]] = set()

    for row in snapshots:
        key = (row.get("snapshot_date", ""), row.get("opportunity_id", ""))

        if not all(key):
            continue

        if key in seen:
            record_issue(
                issues,
                "duplicate_opportunity",
                "forecast_snapshot",
                row.get("forecast_snapshot_id", ""),
                "Opportunity appears more than once on the same snapshot date.",
            )
        else:
            seen.add(key)

    summaries.append(f"Custom anomaly rules: {len(issues)} issue(s)")
    return issues, summaries


def load_ground_truth(path: Path) -> list[dict[str, str]]:
    """Read labelled anomalies for comparison after validation."""
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_report(
    report_path: Path,
    data_dir: Path,
    summaries: list[str],
    issues: list[dict[str, str]],
    ground_truth: list[dict[str, str]] | None,
) -> None:
    """Write validation summaries, detected issues, and optional recall."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Data Validation Report",
        "",
        f"- Data directory: `{data_dir}`",
        f"- Custom anomaly issues detected: **{len(issues)}**",
        "",
        "## Check summaries",
        "",
    ]

    lines.extend(f"- {summary}" for summary in summaries)
    lines.extend(["", "## Detected issues", ""])

    if issues:
        for issue in issues:
            lines.append(
                f"- **{issue['issue_type']}** — {issue['table']} / "
                f"`{issue['record_id']}`: {issue['description']}"
            )
    else:
        lines.append("No custom anomaly issues detected.")

    if ground_truth is not None:
        expected = {
            (row.get("issue_type", ""), row.get("record_id", ""))
            for row in ground_truth
        }
        detected = {
            (row.get("issue_type", ""), row.get("record_id", ""))
            for row in issues
        }

        matched = expected & detected
        recall = len(matched) / len(expected) if expected else 1.0

        lines.extend([
            "",
            "## Ground-truth comparison",
            "",
            f"- Ground-truth anomalies: {len(expected)}",
            f"- Matched detections: {len(matched)}",
            f"- Recall: **{recall:.0%}**",
        ])

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a sales forecasting dataset."
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Directory containing the CSV data tables.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        parser.error(f"Data directory does not exist: {data_dir}")

    # Complete validation before reading ground truth for recall comparison.
    issues, summaries = run_checks(data_dir)

    truth_path = data_dir / "ground_truth.csv"
    ground_truth = load_ground_truth(truth_path) if truth_path.exists() else None

    report_path = data_dir.parent / "processed" / "validation_report.md"
    write_report(report_path, data_dir, summaries, issues, ground_truth)

    print(f"Validation complete for {data_dir}")
    print(f"Custom anomaly issues detected: {len(issues)}")

    if ground_truth is not None:
        expected = {
            (row.get("issue_type", ""), row.get("record_id", ""))
            for row in ground_truth
        }
        detected = {
            (row.get("issue_type", ""), row.get("record_id", ""))
            for row in issues
        }

        matched = len(expected & detected)
        recall = matched / len(expected) if expected else 1.0
        print(f"Ground-truth recall: {matched}/{len(expected)} ({recall:.0%})")

    print(f"Report written to: {report_path}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())