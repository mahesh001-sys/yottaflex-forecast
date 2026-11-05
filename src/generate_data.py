"""Deterministic synthetic master and opportunity data generator.

Run from the repository root:
    python -m src.generate_data --scale starter --out data/raw
    python -m src.generate_data --scale full --out data/raw
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SEED = 20261022
START_DATE = pd.Timestamp("2025-01-01")
END_DATE = pd.Timestamp("2026-12-31")
AS_OF_DATE = END_DATE

SCALES = {
    "starter": {"territories": 4, "reps": 20, "accounts": 20, "opportunities": 200},
    "full": {"territories": 4, "reps": 2000, "accounts": 2000, "opportunities": 20000},
}

STAGES = [
    ("STAGE-001", "Prospecting", 1, 0.10, False),
    ("STAGE-002", "Qualification", 2, 0.25, False),
    ("STAGE-003", "Proposal", 3, 0.50, False),
    ("STAGE-004", "Negotiation", 4, 0.80, False),
    ("STAGE-005", "Closed Won", 5, 1.00, True),
    ("STAGE-006", "Closed Lost", 6, 0.00, True),
]
STAGE_ID = {row[1]: row[0] for row in STAGES}
QUARTER_INDEX = {1: 0.90, 2: 0.95, 3: 1.00, 4: 1.15}
PRODUCTS = ["Platform", "Analytics", "Automation", "Integration", "Support"]
INDUSTRIES = [
    "Technology", "Healthcare", "Manufacturing", "Retail", "Finance",
    "Education", "Logistics", "Telecommunications",
]
REGIONS = ["North", "South", "East", "West"]


def _date_strings(values: Any) -> list[str]:
    return [pd.Timestamp(value).strftime("%Y-%m-%d") for value in values]


def _make_territories(n: int) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "territory_id": f"TER-{i:04d}",
            "territory_name": f"Territory {i:02d}",
            "region": REGIONS[(i - 1) % len(REGIONS)],
            "country_code": "US",
            "created_at": f"2025-01-{min(i, 28):02d}T09:00:00Z",
            "status": "Active",
        })
    return pd.DataFrame(rows)


def _make_stages() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "stage_id": sid,
            "stage_name": name,
            "stage_order": order,
            "default_probability": probability,
            "is_closed_stage": closed,
        }
        for sid, name, order, probability, closed in STAGES
    ])


def _make_reps(n: int, rng: np.random.Generator) -> pd.DataFrame:
    hire_offsets = rng.integers(0, 540, size=n)
    rows = []
    for i in range(1, n + 1):
        hire = START_DATE + pd.Timedelta(days=int(hire_offsets[i - 1]))
        rows.append({
            "rep_id": f"REP-{i:06d}",
            "rep_name": f"Sales Representative {i:04d}",
            "email": f"rep{i:06d}@example.test",
            "hire_date": hire.strftime("%Y-%m-%d"),
            "employment_status": "Active",
            "created_at": f"{hire.strftime('%Y-%m-%d')}T09:00:00Z",
        })
    return pd.DataFrame(rows)


def _make_accounts(
    n: int, territory_ids: list[str], rng: np.random.Generator
) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        territory = territory_ids[int(rng.integers(0, len(territory_ids)))]
        rows.append({
            "account_id": f"ACC-{i:06d}",
            "account_name": f"Synthetic Account {i:06d}",
            "industry": INDUSTRIES[(i - 1) % len(INDUSTRIES)],
            "account_status": "Prospect",
            "territory_id": territory,
            "created_at": (
                f"{(START_DATE + pd.Timedelta(days=(i * 17) % 700)).strftime('%Y-%m-%d')}"
                "T10:00:00Z"
            ),
        })
    return pd.DataFrame(rows)


def _make_assignments(
    reps: pd.DataFrame, territory_ids: list[str], rng: np.random.Generator
) -> pd.DataFrame:
    """Create non-overlapping primary territory intervals; some reps transfer."""
    rows = []
    seq = 1
    transfer_count = max(1, int(len(reps) * 0.20))
    transfer_reps = set(
        rng.choice(reps["rep_id"].to_numpy(), size=transfer_count, replace=False).tolist()
    )
    for idx, rep_id in enumerate(reps["rep_id"]):
        first = territory_ids[idx % len(territory_ids)]
        if rep_id in transfer_reps:
            second = territory_ids[(idx + 1) % len(territory_ids)]
            transfer_day = 365 + (idx % 120)
            transfer_date = START_DATE + pd.Timedelta(days=transfer_day)
            rows.append({
                "assignment_id": f"RTA-{seq:06d}",
                "rep_id": rep_id,
                "territory_id": first,
                "effective_from": "2025-01-01",
                "effective_to": transfer_date.strftime("%Y-%m-%d"),
            })
            seq += 1
            rows.append({
                "assignment_id": f"RTA-{seq:06d}",
                "rep_id": rep_id,
                "territory_id": second,
                "effective_from": transfer_date.strftime("%Y-%m-%d"),
                "effective_to": None,
            })
            seq += 1
        else:
            rows.append({
                "assignment_id": f"RTA-{seq:06d}",
                "rep_id": rep_id,
                "territory_id": first,
                "effective_from": "2025-01-01",
                "effective_to": None,
            })
            seq += 1
    return pd.DataFrame(rows)


def _activity_tier(rep_number: int) -> int:
    """Stable synthetic rep activity tier (1=low, 2=medium, 3=high)."""
    return 1 + ((rep_number * 7) % 3)


def _make_opportunities(
    n: int,
    reps: pd.DataFrame,
    accounts: pd.DataFrame,
    assignments: pd.DataFrame,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create opportunities and their event history/activity, with activity driving wins."""
    rep_ids = reps["rep_id"].tolist()
    account_ids = accounts["account_id"].tolist()
    assignment_rows = assignments.to_dict("records")
    rep_number = {rep_id: int(rep_id[-6:]) for rep_id in rep_ids}
    day_values = pd.date_range(START_DATE, END_DATE, freq="D")
    weights = np.array([QUARTER_INDEX[d.quarter] for d in day_values], dtype=float)
    weights /= weights.sum()
    created_dates = pd.to_datetime(
        rng.choice(day_values.to_numpy(), size=n, replace=True, p=weights)
    )
    base_amounts = rng.lognormal(mean=9.5, sigma=0.85, size=n)
    rows, history, activities = [], [], []

    for i in range(n):
        created = pd.Timestamp(created_dates[i]).normalize()
        age_days = max(0, (AS_OF_DATE - created).days)
        rep_id = rep_ids[int(rng.integers(0, len(rep_ids)))]
        account_id = account_ids[int(rng.integers(0, len(account_ids)))]
        rep_assignments = [a for a in assignment_rows if a["rep_id"] == rep_id]
        active_assignment = next(
            (
                a for a in rep_assignments
                if pd.Timestamp(a["effective_from"]) <= created
                and (
                    a["effective_to"] is None
                    or created < pd.Timestamp(a["effective_to"])
                )
            ),
            rep_assignments[0],
        )
        territory_id = active_assignment["territory_id"]
        expected_close = min(
            created + pd.Timedelta(days=int(rng.integers(30, 181))),
            AS_OF_DATE + pd.Timedelta(days=180),
        )
        amount = round(float(base_amounts[i] * QUARTER_INDEX[created.quarter]), 2)
        opportunity_id = f"OPP-{created.year}-{i + 1:06d}"
        tier = _activity_tier(rep_number[rep_id])

        # Activity is generated before the outcome. More meaningful touches raise the
        # probability of reaching Won; activity is still synthetic and reproducible.
        n_activity = int(rng.integers(2, 9))
        activity_days = sorted(
            set(
                int(x)
                for x in rng.integers(0, max(1, age_days + 1), size=n_activity)
            )
        )
        if not activity_days:
            activity_days = [0]
        touch_score = sum(
            1.0 if (j % 3) != 0 else 1.4
            for j, _ in enumerate(activity_days)
        ) + (tier - 2) * 1.5
        effective_age = age_days + (tier - 2) * 35
        if effective_age < 45:
            path = ["Prospecting"]
        elif effective_age < 110:
            path = ["Prospecting", "Qualification"]
        elif effective_age < 190:
            path = ["Prospecting", "Qualification", "Proposal"]
        elif effective_age < 285:
            path = ["Prospecting", "Qualification", "Proposal", "Negotiation"]
        else:
            # A high touch score and sufficient age are required for a Won outcome.
            terminal = (
                "Closed Won"
                if touch_score >= 8.0 and effective_age >= 330
                else "Closed Lost"
            )
            path = [
                "Prospecting", "Qualification", "Proposal", "Negotiation", terminal
            ]

        for j, day in enumerate(activity_days, start=1):
            kind = ("Call", "Email", "Meeting")[(i + j) % 3]
            activities.append({
                "activity_id": f"ACT-{opportunity_id}-{j:03d}",
                "opportunity_id": opportunity_id,
                "rep_id": rep_id,
                "activity_type": kind,
                "activity_date": (
                    created + pd.Timedelta(days=min(day, age_days))
                ).strftime("%Y-%m-%d"),
                "subject": f"Synthetic {kind.lower()} touchpoint",
                "outcome": "Completed",
            })

        for seq, stage_name in enumerate(path, start=1):
            if seq == 1:
                event_day = 0
            else:
                event_day = min(
                    max(0, int(age_days * seq / max(1, len(path)))),
                    age_days,
                )
            changed_at = created + pd.Timedelta(days=event_day)
            history.append({
                "stage_history_id": f"STG-{opportunity_id}-{seq:03d}",
                "opportunity_id": opportunity_id,
                "from_stage_id": STAGE_ID[path[seq - 2]] if seq > 1 else None,
                "to_stage_id": STAGE_ID[stage_name],
                "changed_by_rep_id": rep_id,
                "changed_at": changed_at.strftime("%Y-%m-%dT09:00:00Z"),
                "reason": "Synthetic activity-informed lifecycle progression",
                "event_sequence": seq,
            })

        terminal = path[-1]
        outcome = (
            "Won" if terminal == "Closed Won"
            else ("Lost" if terminal == "Closed Lost" else "Open")
        )
        closed_date = history[-1]["changed_at"][:10] if outcome != "Open" else None
        rows.append({
            "opportunity_id": opportunity_id,
            "opportunity_name": f"{PRODUCTS[i % len(PRODUCTS)]} opportunity {i + 1:06d}",
            "account_id": account_id,
            "owner_rep_id": rep_id,
            "territory_id": territory_id,
            "source_opportunity_id": None,
            "created_date": created.strftime("%Y-%m-%d"),
            "expected_close_date": expected_close.strftime("%Y-%m-%d"),
            "amount": f"{amount:.2f}",
            "currency_code": "USD",
            "product": PRODUCTS[i % len(PRODUCTS)],
            "current_stage": terminal,
            "closed_date": closed_date,
            "outcome": outcome,
        })

    opportunities = pd.DataFrame(rows)
    stage_history = pd.DataFrame(history)
    activity = pd.DataFrame(activities)
    won_accounts = set(
        opportunities.loc[opportunities["outcome"] == "Won", "account_id"]
    )
    accounts = accounts.copy()
    accounts.loc[
        accounts["account_id"].isin(won_accounts), "account_status"
    ] = "Customer"
    return opportunities, stage_history, activity, accounts


def _make_quota(reps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rep_id in reps["rep_id"]:
        for quarter in pd.period_range("2025Q1", "2026Q4", freq="Q"):
            rows.append({
                "quota_id": f"QUOTA-{rep_id}-{quarter}",
                "rep_id": rep_id,
                "fiscal_quarter": str(quarter),
                "quota_amount": "250000.00",
                "currency_code": "USD",
            })
    return pd.DataFrame(rows)


def _make_bookings(opportunities: pd.DataFrame) -> pd.DataFrame:
    won = opportunities.loc[opportunities["outcome"] == "Won"]
    return pd.DataFrame([{
        "booking_id": f"BOOK-{row.opportunity_id}",
        "opportunity_id": row.opportunity_id,
        "account_id": row.account_id,
        "rep_id": row.owner_rep_id,
        "booking_date": row.closed_date,
        "booking_amount": f"{float(row.amount):.2f}",
        "currency_code": row.currency_code,
    } for row in won.itertuples(index=False)])


def _make_snapshots(
    opportunities: pd.DataFrame,
    stage_history: pd.DataFrame,
    activity: pd.DataFrame,
) -> pd.DataFrame:
    """Reconstruct each snapshot from events on/before the fixed date only."""
    dates = pd.date_range("2025-01-31", "2026-12-31", freq="M")
    history = stage_history.copy()
    history["event_date"] = (
        pd.to_datetime(history["changed_at"], utc=True)
        .dt.tz_localize(None)
        .dt.normalize()
    )
    activity = activity.copy()
    activity["event_date"] = pd.to_datetime(activity["activity_date"])

    # Sort each opportunity's activity dates once. This avoids repeatedly
    # filtering the entire activity table for every opportunity and snapshot.
    activity_dates = {
        opp_id: group["event_date"].sort_values().to_numpy(dtype="datetime64[ns]")
        for opp_id, group in activity.groupby("opportunity_id")
    }

    opps = opportunities.copy()
    for col in ("created_date", "expected_close_date"):
        opps[col] = pd.to_datetime(opps[col])

    rows = []
    seq_by_date = {}
    for snapshot_date in dates:
        known = history.loc[
            history["event_date"] <= snapshot_date
        ].sort_values(["event_date", "event_sequence"])
        latest = (
            known.drop_duplicates("opportunity_id", keep="last")
            .set_index("opportunity_id")
        )

        for opp in opps.itertuples(index=False):
            if opp.created_date > snapshot_date:
                continue

            hist = (
                latest.loc[opp.opportunity_id]
                if opp.opportunity_id in latest.index
                else None
            )
            if hist is None:
                continue

            stage_name = next(
                name for sid, name, *_ in STAGES
                if sid == hist["to_stage_id"]
            )
            if stage_name in ("Closed Won", "Closed Lost"):
                continue

            opp_acts = activity_dates.get(
                opp.opportunity_id,
                np.array([], dtype="datetime64[ns]"),
            )
            cutoff = np.searchsorted(
                opp_acts,
                snapshot_date.to_datetime64(),
                side="right",
            )
            last_activity = (
                pd.Timestamp(opp_acts[cutoff - 1]) if cutoff else pd.NaT
            )

            stale_days = (
                int((snapshot_date - last_activity).days)
                if pd.notna(last_activity)
                else int((snapshot_date - opp.created_date).days)
            )

            # Deterministic slippage based only on prior activity and stage events.
            pushes = max(0, (stale_days - 30) // 30)
            close_date = opp.expected_close_date + pd.Timedelta(days=30 * pushes)
            key = snapshot_date.strftime("%Y-%m-%d")
            seq_by_date[key] = seq_by_date.get(key, 0) + 1
            rows.append({
                "forecast_snapshot_id": f"FCST-{key}-{seq_by_date[key]:03d}",
                "snapshot_date": key,
                "opportunity_id": opp.opportunity_id,
                "stage_id": hist["to_stage_id"],
                "amount": opp.amount,
                "expected_close_date": close_date.strftime("%Y-%m-%d"),
                "last_activity_date": (
                    last_activity.strftime("%Y-%m-%d")
                    if pd.notna(last_activity)
                    else None
                ),
                "stale_days": stale_days,
                "is_stale": stale_days >= 30,
            })

    return pd.DataFrame(rows)


def generate_dataset(
    scale: str = "starter",
    out: str | Path = "data/raw",
    seed: int = SEED,
) -> dict[str, pd.DataFrame]:
    if scale not in SCALES:
        raise ValueError(f"Unsupported scale {scale!r}; choose starter or full.")

    rng = np.random.default_rng(seed)
    config = SCALES[scale]
    territories = _make_territories(config["territories"])
    stages = _make_stages()
    reps = _make_reps(config["reps"], rng)
    accounts = _make_accounts(
        config["accounts"], territories["territory_id"].tolist(), rng
    )
    assignments = _make_assignments(
        reps, territories["territory_id"].tolist(), rng
    )
    opportunities, stage_history, activity, accounts = _make_opportunities(
        config["opportunities"], reps, accounts, assignments, rng
    )

    datasets = {
        "territory": territories,
        "stage": stages,
        "sales_rep": reps,
        "account": accounts,
        "rep_territory_assignment": assignments,
        "opportunity": opportunities,
        "stage_history": stage_history,
        "activity": activity,
        "quota": _make_quota(reps),
        "historical_booking": _make_bookings(opportunities),
        "forecast_snapshot": _make_snapshots(
            opportunities, stage_history, activity
        ),
    }

    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    for name, frame in datasets.items():
        frame.to_csv(out_path / f"{name}.csv", index=False)

    return datasets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic YottaFlex sales data."
    )
    parser.add_argument("--scale", choices=sorted(SCALES), required=True)
    parser.add_argument("--out", default="data/raw")
    args = parser.parse_args()

    datasets = generate_dataset(args.scale, args.out, SEED)
    print(f"Generated {args.scale} dataset in {args.out} (seed={SEED}):")
    for name, frame in datasets.items():
        print(f"  {name}: {len(frame):,} rows")


if __name__ == "__main__":
    main()