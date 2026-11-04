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
INDUSTRIES = ["Technology", "Healthcare", "Manufacturing", "Retail", "Finance",
              "Education", "Logistics", "Telecommunications"]
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
        {"stage_id": sid, "stage_name": name, "stage_order": order,
         "default_probability": probability, "is_closed_stage": closed}
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


def _make_accounts(n: int, territory_ids: list[str], rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        territory = territory_ids[int(rng.integers(0, len(territory_ids)))]
        rows.append({
            "account_id": f"ACC-{i:06d}",
            "account_name": f"Synthetic Account {i:06d}",
            "industry": INDUSTRIES[(i - 1) % len(INDUSTRIES)],
            "account_status": "Prospect",
            "territory_id": territory,
            "created_at": f"{(START_DATE + pd.Timedelta(days=(i * 17) % 700)).strftime('%Y-%m-%d')}T10:00:00Z",
        })
    return pd.DataFrame(rows)


def _make_assignments(reps: pd.DataFrame, territory_ids: list[str],
                      rng: np.random.Generator) -> pd.DataFrame:
    """Create non-overlapping primary territory intervals; some reps transfer."""
    rows = []
    seq = 1
    transfer_count = max(1, int(len(reps) * 0.20))
    transfer_reps = set(rng.choice(reps["rep_id"].to_numpy(), size=transfer_count,
                                   replace=False).tolist())
    for idx, rep_id in enumerate(reps["rep_id"]):
        first = territory_ids[idx % len(territory_ids)]
        if rep_id in transfer_reps:
            second = territory_ids[(idx + 1) % len(territory_ids)]
            transfer_day = 365 + (idx % 120)
            transfer_date = START_DATE + pd.Timedelta(days=transfer_day)
            rows.append({
                "assignment_id": f"RTA-{seq:06d}", "rep_id": rep_id,
                "territory_id": first, "effective_from": "2025-01-01",
                "effective_to": transfer_date.strftime("%Y-%m-%d"),
            })
            seq += 1
            rows.append({
                "assignment_id": f"RTA-{seq:06d}", "rep_id": rep_id,
                "territory_id": second, "effective_from": transfer_date.strftime("%Y-%m-%d"),
                "effective_to": None,
            })
            seq += 1
        else:
            rows.append({
                "assignment_id": f"RTA-{seq:06d}", "rep_id": rep_id,
                "territory_id": first, "effective_from": "2025-01-01",
                "effective_to": None,
            })
            seq += 1
    return pd.DataFrame(rows)


def _activity_tier(rep_number: int) -> int:
    """Stable synthetic activity tier (1=low, 2=medium, 3=high), not an outcome label."""
    return 1 + ((rep_number * 7) % 3)


def _progress_opportunity(age_days: int, activity_tier: int) -> tuple[str, int]:
    """Return derived terminal stage and number of stage-history events.

    Progression depends on elapsed deal age and the rep's stable activity tier.
    The scenario key provides deterministic cohort variation; it does not randomly
    assign a Won/Lost label.
    """
    effective_age = age_days + (activity_tier - 2) * 45
    if effective_age < 45:
        return "Prospecting", 1
    if effective_age < 110:
        return "Qualification", 2
    if effective_age < 190:
        return "Proposal", 3
    if effective_age < 285:
        return "Negotiation", 4
    # A terminal decision requires sufficient age and the Negotiation stage.
    # High-activity reps with an older deal reach Won; other eligible deals are Lost.
    # This is a documented deterministic rule, not an independent random label.
    if activity_tier == 3 and effective_age >= 330:
        return "Closed Won", 5
    return "Closed Lost", 5


def _stage_history(opportunity_id: str, created: pd.Timestamp, age_days: int,
                   terminal_stage: str, event_count: int, rep_id: str) -> list[dict[str, Any]]:
    path = ["Prospecting", "Qualification", "Proposal", "Negotiation"]
    if terminal_stage in ("Closed Won", "Closed Lost"):
        path.append(terminal_stage)
    path = path[:event_count]
    if terminal_stage == "Closed Lost" and event_count == 5:
        # Lost may be reached from any open stage; for this scenario use Negotiation.
        pass
    rows = []
    previous = None
    for seq, stage_name in enumerate(path, start=1):
        event_day = min(max(0, int(age_days * seq / max(1, len(path)))), age_days)
        changed_at = created + pd.Timedelta(days=event_day)
        rows.append({
            "stage_history_id": f"STG-{opportunity_id}-{seq:03d}",
            "opportunity_id": opportunity_id,
            "from_stage_id": STAGE_ID[previous] if previous else None,
            "to_stage_id": STAGE_ID[stage_name],
            "changed_by_rep_id": rep_id,
            "changed_at": changed_at.strftime("%Y-%m-%dT09:00:00Z"),
            "reason": "Synthetic deterministic lifecycle progression",
            "event_sequence": seq,
        })
        previous = stage_name
    return rows


def _make_opportunities(n: int, reps: pd.DataFrame, accounts: pd.DataFrame,
                        assignments: pd.DataFrame, rng: np.random.Generator
                        ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rep_ids = reps["rep_id"].tolist()
    account_ids = accounts["account_id"].tolist()
    account_territory = dict(zip(accounts["account_id"], accounts["territory_id"]))
    assignment_rows = assignments.to_dict("records")
    rep_number = {rep_id: int(rep_id[-6:]) for rep_id in rep_ids}

    # Weighted dates create seasonal source volume. Seasonality does not flip outcomes.
    day_values = pd.date_range(START_DATE, END_DATE, freq="D")
    weights = np.array([QUARTER_INDEX[d.quarter] for d in day_values], dtype=float)
    weights /= weights.sum()
    created_dates = rng.choice(day_values.to_numpy(), size=n, replace=True, p=weights)
    created_dates = pd.to_datetime(created_dates)

    # Lognormal-style skew; seasonal multiplier is applied once to source amount.
    base_amounts = rng.lognormal(mean=9.5, sigma=0.85, size=n)
    rows, history = [], []
    for i in range(n):
        created = pd.Timestamp(created_dates[i]).normalize()
        age_days = max(0, (AS_OF_DATE - created).days)
        rep_id = rep_ids[int(rng.integers(0, len(rep_ids)))]
        account_id = account_ids[int(rng.integers(0, len(account_ids)))]
        rep_assignments = [a for a in assignment_rows if a["rep_id"] == rep_id]
        active_assignment = next(
            (a for a in rep_assignments
             if pd.Timestamp(a["effective_from"]) <= created
             and (a["effective_to"] is None or created < pd.Timestamp(a["effective_to"]))),
            rep_assignments[0],
        )
        territory_id = active_assignment["territory_id"]
        # Opportunity's territory is the rep's territory at creation, as specified.
        if territory_id not in account_territory.values():
            territory_id = account_territory[account_id]
        expected_close = created + pd.Timedelta(days=int(rng.integers(30, 181)))
        expected_close = min(expected_close, AS_OF_DATE + pd.Timedelta(days=180))
        quarter_multiplier = QUARTER_INDEX[created.quarter]
        amount = round(float(base_amounts[i] * quarter_multiplier), 2)
        opportunity_id = f"OPP-{created.year}-{i + 1:06d}"

        tier = _activity_tier(rep_number[rep_id])
        terminal, event_count = _progress_opportunity(age_days, tier)
        # A Won path must traverse Negotiation. A Lost path can close from the
        # current open stage; when age permits all four open stages are recorded.
        if terminal == "Closed Lost" and event_count == 5:
            stage_names = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Lost"]
        else:
            stage_names = None
        if stage_names is None:
            hrows = _stage_history(opportunity_id, created, age_days, terminal, event_count, rep_id)
        else:
            hrows = _stage_history(opportunity_id, created, age_days, terminal, event_count, rep_id)
        history.extend(hrows)
        current_stage = terminal
        outcome = "Won" if terminal == "Closed Won" else (
            "Lost" if terminal == "Closed Lost" else "Open"
        )
        closed_date = hrows[-1]["changed_at"][:10] if outcome != "Open" else None
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
            "current_stage": current_stage,
            "closed_date": closed_date,
            "outcome": outcome,
        })

    opportunities = pd.DataFrame(rows)
    stage_history = pd.DataFrame(history)
    # Account status is derived from related opportunity outcomes, never randomized.
    won_accounts = set(opportunities.loc[opportunities["outcome"] == "Won", "account_id"])
    accounts = accounts.copy()
    accounts.loc[accounts["account_id"].isin(won_accounts), "account_status"] = "Customer"
    return opportunities, stage_history, accounts


def generate_dataset(scale: str = "starter", out: str | Path = "data/raw",
                     seed: int = SEED) -> dict[str, pd.DataFrame]:
    if scale not in SCALES:
        raise ValueError(f"Unsupported scale {scale!r}; choose starter or full.")
    rng = np.random.default_rng(seed)
    config = SCALES[scale]
    territories = _make_territories(config["territories"])
    stages = _make_stages()
    reps = _make_reps(config["reps"], rng)
    accounts = _make_accounts(config["accounts"], territories["territory_id"].tolist(), rng)
    assignments = _make_assignments(reps, territories["territory_id"].tolist(), rng)
    opportunities, stage_history, accounts = _make_opportunities(
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
    }
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    for name, frame in datasets.items():
        frame.to_csv(out_path / f"{name}.csv", index=False)
    return datasets


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic YottaFlex sales data.")
    parser.add_argument("--scale", choices=sorted(SCALES), required=True)
    parser.add_argument("--out", default="data/raw")
    args = parser.parse_args()
    generate_dataset(args.scale, args.out, SEED)
    print(f"Generated {SCALES[args.scale]} source rows plus stage history in {args.out} (seed={SEED}).")


if __name__ == "__main__":
    main()
