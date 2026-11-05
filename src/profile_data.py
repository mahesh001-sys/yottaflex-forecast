import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path


def read_csv(data_dir, filename):
    path = Path(data_dir) / filename
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value[:10])


def number(value, default=0.0):
    if value in (None, ""):
        return default
    return float(value)


def quarter_label(value):
    parsed = parse_date(value) if isinstance(value, str) else value
    if parsed is None:
        return None
    quarter = (parsed.month - 1) // 3 + 1
    return f"{parsed.year}Q{quarter}"


def clamp_probability(value):
    return min(1.0, max(0.0, number(value)))


def territory_for_rep(assignments, rep_id, as_of_date):
    """Return the territory active on as_of_date; start is inclusive, end exclusive."""
    for assignment in assignments:
        if assignment["rep_id"] != rep_id:
            continue

        start = parse_date(assignment["effective_from"])
        end = parse_date(assignment.get("effective_to", ""))

        if start and start <= as_of_date and (end is None or as_of_date < end):
            return assignment["territory_id"]

    return None


def stage_as_of(history, opportunity_id, as_of_date):
    """Return the latest stage reached on or before as_of_date."""
    eligible = []

    for event in history:
        if event["opportunity_id"] != opportunity_id:
            continue

        changed_at = event.get("changed_at", "")
        changed_date = parse_date(changed_at)
        if changed_date and changed_date <= as_of_date:
            eligible.append(event)

    if not eligible:
        return None

    eligible.sort(
        key=lambda event: (
            event.get("changed_at", ""),
            int(event.get("event_sequence") or 0),
        )
    )
    return eligible[-1]["to_stage_id"]


def require_variation(label, values, failures):
    distinct = {round(float(value), 8) for value in values if value is not None}
    if len(distinct) < 2:
        failures.append(
            f"{label}: no variation found (need at least two distinct values; "
            f"found {len(distinct)})."
        )


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]

    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")

    return "\n".join(lines)


def build_report(data_dir):
    opportunities = read_csv(data_dir, "opportunity.csv")
    stages = read_csv(data_dir, "stage.csv")
    sales_reps = read_csv(data_dir, "sales_rep.csv")
    activities = read_csv(data_dir, "activity.csv")
    snapshots = read_csv(data_dir, "forecast_snapshot.csv")
    quotas = read_csv(data_dir, "quota.csv")
    bookings = read_csv(data_dir, "historical_booking.csv")
    assignments = read_csv(data_dir, "rep_territory_assignment.csv")

    failures = []
    report = ["# Data Distribution Profile", ""]

    # Stage lookup is used to support either stage IDs or stage names in opportunities.
    stage_names = {
        row.get("stage_id", ""): row.get("stage_name", row.get("stage_id", ""))
        for row in stages
    }
    stage_names.update(
        {
            row.get("stage_name", ""): row.get("stage_name", "")
            for row in stages
        }
    )

    # Amount distribution.
    amounts = sorted(number(row.get("amount")) for row in opportunities)
    if not amounts:
        failures.append("Amount distribution: no opportunity rows found.")
        percentiles = []
    else:
        percentiles = []
        for percentile in (0, 25, 50, 75, 90, 95, 100):
            position = (len(amounts) - 1) * percentile / 100
            lower = int(position)
            upper = min(lower + 1, len(amounts) - 1)
            fraction = position - lower
            value = amounts[lower] + (amounts[upper] - amounts[lower]) * fraction
            percentiles.append((f"P{percentile}", f"{value:,.2f}"))

        require_variation("Opportunity amounts", amounts, failures)

    report.extend(["## Opportunity amount percentiles", ""])
    report.append(markdown_table(["Percentile", "Amount"], percentiles))
    report.append("")

    # Counts by stage, product, and territory.
    report.append("## Opportunities by stage")
    report.append("")
    stage_counts = Counter(
        stage_names.get(row.get("current_stage", ""), row.get("current_stage", "Unknown"))
        for row in opportunities
    )
    report.append(
        markdown_table(["Stage", "Count"], sorted(stage_counts.items()))
    )
    report.append("")

    report.append("## Opportunities by product")
    report.append("")
    product_counts = Counter(row.get("product") or "Unknown" for row in opportunities)
    report.append(markdown_table(["Product", "Count"], sorted(product_counts.items())))
    report.append("")

    report.append("## Opportunities by territory")
    report.append("")
    territory_counts = Counter(
        row.get("territory_id") or "Unknown" for row in opportunities
    )
    report.append(
        markdown_table(["Territory", "Count"], sorted(territory_counts.items()))
    )
    report.append("")

    # Win rate by close quarter.
    closed_by_quarter = defaultdict(lambda: {"won": 0, "lost": 0})
    for row in opportunities:
        outcome = (row.get("outcome") or "").strip().lower()
        closed_date = parse_date(row.get("closed_date", ""))
        if not closed_date or outcome not in {"won", "lost"}:
            continue

        quarter = quarter_label(closed_date)
        closed_by_quarter[quarter]["won" if outcome == "won" else "lost"] += 1

    win_rate_rows = []
    win_rates = []
    for quarter in sorted(closed_by_quarter):
        counts = closed_by_quarter[quarter]
        total = counts["won"] + counts["lost"]
        rate = counts["won"] / total if total else 0.0
        win_rates.append(rate)
        win_rate_rows.append(
            (quarter, counts["won"], counts["lost"], f"{rate:.1%}")
        )

    require_variation("Quarterly win rates", win_rates, failures)
    report.extend(["## Win rate by close quarter", ""])
    report.append(
        markdown_table(["Quarter", "Won", "Lost", "Win rate"], win_rate_rows)
    )
    report.append("")

    # Slippage by close quarter: closed after the opportunity's recorded expected close date.
    slippage_by_quarter = defaultdict(lambda: {"late": 0, "closed": 0})
    for row in opportunities:
        closed_date = parse_date(row.get("closed_date", ""))
        expected_date = parse_date(row.get("expected_close_date", ""))
        outcome = (row.get("outcome") or "").strip().lower()

        if not closed_date or outcome not in {"won", "lost"}:
            continue

        quarter = quarter_label(closed_date)
        slippage_by_quarter[quarter]["closed"] += 1
        if expected_date and closed_date > expected_date:
            slippage_by_quarter[quarter]["late"] += 1

    slippage_rows = []
    slippage_rates = []
    for quarter in sorted(slippage_by_quarter):
        counts = slippage_by_quarter[quarter]
        rate = counts["late"] / counts["closed"] if counts["closed"] else 0.0
        slippage_rates.append(rate)
        slippage_rows.append(
            (quarter, counts["late"], counts["closed"], f"{rate:.1%}")
        )

    require_variation("Quarterly slippage rates", slippage_rates, failures)
    report.extend(
        [
            "## Slippage rate by close quarter",
            "",
            "Slippage means a closed opportunity closed after its recorded expected close date.",
            "",
        ]
    )
    report.append(
        markdown_table(["Quarter", "Late closes", "Closed deals", "Slippage rate"], slippage_rows)
    )
    report.append("")

    # Stale-deal rate by snapshot date.
    stale_by_snapshot = defaultdict(lambda: {"stale": 0, "total": 0})
    for row in snapshots:
        snapshot_date = row.get("snapshot_date", "")
        if not snapshot_date:
            continue

        counts = stale_by_snapshot[snapshot_date]
        counts["total"] += 1
        if str(row.get("is_stale", "")).strip().lower() in {"true", "1", "yes"}:
            counts["stale"] += 1

    stale_rows = []
    stale_rates = []
    for snapshot_date in sorted(stale_by_snapshot):
        counts = stale_by_snapshot[snapshot_date]
        rate = counts["stale"] / counts["total"] if counts["total"] else 0.0
        stale_rates.append(rate)
        stale_rows.append(
            (snapshot_date, counts["stale"], counts["total"], f"{rate:.1%}")
        )

    require_variation("Stale-deal rates by snapshot date", stale_rates, failures)
    report.extend(["## Stale-deal rate by snapshot date", ""])
    report.append(
        markdown_table(["Snapshot date", "Stale", "Open deals", "Stale rate"], stale_rows)
    )
    report.append("")

    # Activities per rep, retaining reps with no activities.
    activity_counts = Counter(row.get("rep_id", "") for row in activities)
    rep_ids = sorted(
        {
            row.get("rep_id", "")
            for row in sales_reps
            if row.get("rep_id", "")
        }
    )
    activity_values = [activity_counts.get(rep_id, 0) for rep_id in rep_ids]
    require_variation("Activities per rep", activity_values, failures)

    report.extend(["## Activities per rep", ""])
    report.append(
        markdown_table(
            ["Rep ID", "Activity count"],
            [(rep_id, activity_counts.get(rep_id, 0)) for rep_id in rep_ids],
        )
    )
    report.append("")

    # Quota attainment by rep-quarter, using bookings as achieved revenue.
    booking_totals = defaultdict(float)
    for row in bookings:
        quarter = quarter_label(row.get("booking_date", ""))
        rep_id = row.get("rep_id", "")
        if quarter and rep_id:
            booking_totals[(rep_id, quarter)] += number(row.get("booking_amount"))

    attainment_rows = []
    attainment_values = []
    for row in quotas:
        rep_id = row.get("rep_id", "")
        quarter = row.get("fiscal_quarter", "")
        quota_amount = number(row.get("quota_amount"))
        booked = booking_totals.get((rep_id, quarter), 0.0)
        attainment = booked / quota_amount if quota_amount else 0.0
        attainment_values.append(attainment)
        attainment_rows.append(
            (rep_id, quarter, f"{quota_amount:,.2f}", f"{booked:,.2f}", f"{attainment:.1%}")
        )

    require_variation("Quota attainment", attainment_values, failures)
    report.extend(
        [
            "## Quota attainment by rep-quarter",
            "",
            markdown_table(
                ["Rep ID", "Quarter", "Quota", "Bookings", "Attainment"],
                attainment_rows,
            ),
            "",
        ]
    )

    if attainment_values:
        sorted_attainment = sorted(attainment_values)

        def percentile(values, p):
            position = (len(values) - 1) * p
            lower = int(position)
            upper = min(lower + 1, len(values) - 1)
            fraction = position - lower
            return values[lower] + (values[upper] - values[lower]) * fraction

        report.extend(
            [
                "### Quota attainment spread",
                "",
                markdown_table(
                    ["Measure", "Attainment"],
                    [
                        ("Minimum", f"{min(sorted_attainment):.1%}"),
                        ("25th percentile", f"{percentile(sorted_attainment, 0.25):.1%}"),
                        ("Median", f"{percentile(sorted_attainment, 0.50):.1%}"),
                        ("75th percentile", f"{percentile(sorted_attainment, 0.75):.1%}"),
                        ("Maximum", f"{max(sorted_attainment):.1%}"),
                    ],
                ),
                "",
            ]
        )

    # Include the helpers' intended boundary semantics in the report.
    report.extend(
        [
            "## Boundary conventions",
            "",
            "- Quarter dates are assigned by calendar quarter; March 31 is Q1 and April 1 is Q2.",
            "- Territory assignments include `effective_from` and exclude `effective_to`.",
            "- Stage-history events on the snapshot date are included when resolving the stage as of that date.",
            "- Probabilities are bounded to the inclusive range 0%–100%.",
            "",
        ]
    )

    report.extend(["## Validation", ""])
    if failures:
        report.append("**FAIL**")
        report.extend(f"- {failure}" for failure in failures)
    else:
        report.append("**PASS** — all checked numeric distributions show variation.")

    return "\n".join(report) + "\n", failures


def main():
    parser = argparse.ArgumentParser(
        description="Profile the generated sales forecasting data."
    )
    parser.add_argument(
        "--data-dir",
        default="data/raw",
        help="Directory containing the raw CSV files (default: data/raw).",
    )
    args = parser.parse_args()

    try:
        report, failures = build_report(args.data_dir)
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    output_path = Path(args.data_dir).parent / "processed" / "distribution_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"Report written to: {output_path}")
    if failures:
        for failure in failures:
            print(f"FAIL | {failure}")
        return 1

    print("PASS | All checked numeric distributions show variation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())