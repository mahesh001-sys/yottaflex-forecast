# Data Dictionary

## Conventions

- Types are logical types; for SQLite use `TEXT` for IDs/dates/timestamps, `INTEGER` for whole numbers/booleans, and `NUMERIC` for money/rates, with explicit validation.
- Required means NOT NULL for a persisted row. Optional means NULL is allowed under the stated condition.
- All monetary fields use USD and two decimal places unless stated otherwise.
- Timestamps are UTC ISO 8601; dates use `YYYY-MM-DD`.
- Controlled values are case-sensitive and must match the spelling shown.
- `created_at` values are synthetic. IDs are deterministic and unique.

## SalesRep

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| rep_id | TEXT | Yes | `REP-` + 6 digits | Yes (PK) | Match `^REP-[0-9]{6}$`; deterministic sequence |
| rep_name | TEXT | Yes | Non-empty name | No | Trim whitespace; 1–120 characters |
| email | TEXT | Yes | Synthetic email address | Yes | Valid email shape; lowercase; max 254 chars |
| hire_date | DATE | Yes | Calendar date | No | Valid date; not after synthetic dataset end date |
| employment_status | TEXT | Yes | `Active`, `Inactive` | No | Must be in enum |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## Territory

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| territory_id | TEXT | Yes | `TER-` + 6 digits | Yes (PK) | Match `^TER-[0-9]{6}$` |
| territory_name | TEXT | Yes | Non-empty territory label | Yes | Trimmed; 1–100 chars |
| region | TEXT | Yes | Synthetic region label | No | 1–80 chars |
| country_code | TEXT | Yes | ISO 3166-1 alpha-2 code | No | Exactly two uppercase letters |
| territory_status | TEXT | Yes | `Active`, `Inactive` | No | Must be in enum |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## Account

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| account_id | TEXT | Yes | `ACC-` + 6 digits | Yes (PK) | Match `^ACC-[0-9]{6}$` |
| account_name | TEXT | Yes | Synthetic organization name | No | 1–160 chars after trimming |
| industry | TEXT | Yes | Controlled synthetic industry label | No | Must be in configured industry catalogue |
| account_status | TEXT | Yes | `Prospect`, `Customer`, `Disqualified` | No | Must be in enum; Customer requires qualifying Won booking/outcome under conversion rule |
| territory_id | TEXT | No | Territory ID | No (FK) | If present, must reference Territory |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## Opportunity

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| opportunity_id | TEXT | Yes | `OPP-YYYY-` + 6 digits | Yes (PK) | Match `^OPP-[0-9]{4}-[0-9]{6}$`; year matches creation cohort |
| opportunity_name | TEXT | Yes | Synthetic deal label | No | 1–160 chars |
| account_id | TEXT | Yes | Account ID | No (FK) | Must reference Account |
| owner_rep_id | TEXT | Yes | Rep ID | No (FK) | Must reference SalesRep |
| territory_id | TEXT | Yes | Territory ID | No (FK) | Must reference Territory and be consistent with effective assignment at creation |
| source_opportunity_id | TEXT | No | Opportunity ID | No (self-FK) | If present, must reference an existing opportunity; use for renewal/expansion lineage only |
| created_date | DATE | Yes | Calendar date | No | Valid date; no later than dataset end |
| expected_close_date | DATE | Yes | Calendar date | No | On or after created_date |
| amount | NUMERIC(14,2) | Yes | USD; greater than 0 | No | Finite positive amount; two decimal places |
| currency_code | TEXT | Yes | `USD` | No | Must equal `USD` for this POC |
| current_stage | TEXT | Yes | Six configured stage names | No | Derived from latest StageHistory event; must agree with it |
| closed_date | DATE | No | Calendar date | No | Required iff stage is Closed Won/Lost; on or after created_date |
| outcome | TEXT | Yes | `Open`, `Won`, `Lost` | No | Derived: Open for open stages, Won for Closed Won, Lost for Closed Lost |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## Stage

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| stage_id | TEXT | Yes | `STGDEF-` + 3 digits | Yes (PK) | Match `^STGDEF-[0-9]{3}$` |
| stage_name | TEXT | Yes | `Prospecting`, `Qualification`, `Proposal`, `Negotiation`, `Closed Won`, `Closed Lost` | Yes | Must be one of the six names |
| stage_order | INTEGER | Yes | 1–6 | Yes | Prospecting=1, Qualification=2, Proposal=3, Negotiation=4, Closed Won=5, Closed Lost=6 |
| default_probability | NUMERIC(5,4) | Yes | 0.0000–1.0000; proportion | No | Must match `assumptions.md` exactly for each stage |
| is_closed_stage | INTEGER/BOOLEAN | Yes | `0`, `1` | No | 1 only for Closed Won and Closed Lost |

## StageHistory

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| stage_history_id | TEXT | Yes | `STH-` + 6 digits | Yes (PK) | Match `^STH-[0-9]{6}$` |
| opportunity_id | TEXT | Yes | Opportunity ID | No (FK) | Must reference Opportunity |
| event_sequence | INTEGER | Yes | Positive integer | Yes per opportunity | Starts at 1 and increments by 1 per opportunity |
| from_stage_id | TEXT | No | Stage ID | No (FK) | NULL only for initial event; otherwise equals prior event's to_stage_id |
| to_stage_id | TEXT | Yes | Stage ID | No (FK) | Initial event must be Prospecting; later transitions must follow allowed graph |
| changed_at | TIMESTAMP | Yes | UTC timestamp | No | Strictly increasing within opportunity; not before opportunity creation |
| changed_by_rep_id | TEXT | No | Rep ID | No (FK) | If present, must reference SalesRep |
| reason | TEXT | No | Controlled reason or short note | No | Max 500 chars; no fabricated customer personal data |

## Activity

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| activity_id | TEXT | Yes | `ACT-` + 6 digits | Yes (PK) | Match `^ACT-[0-9]{6}$` |
| account_id | TEXT | Yes | Account ID | No (FK) | Must reference Account |
| opportunity_id | TEXT | No | Opportunity ID | No (FK) | If present, opportunity's account_id must equal activity.account_id |
| rep_id | TEXT | Yes | Rep ID | No (FK) | Must reference SalesRep |
| activity_type | TEXT | Yes | `Call`, `Email`, `Meeting`, `Demo`, `Task` | No | Must be in enum |
| occurred_at | TIMESTAMP | Yes | UTC timestamp | No | Valid timestamp; not before account creation |
| activity_status | TEXT | Yes | `Planned`, `Completed`, `Cancelled` | No | Must be in enum |
| outcome | TEXT | No | `Connected`, `No Answer`, `Positive`, `Neutral`, `Negative`, `Rescheduled` | No | NULL for planned/cancelled where no result exists; otherwise enum |
| notes | TEXT | No | Synthetic short note | No | Max 1,000 chars; synthetic content only |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## Quota

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| quota_id | TEXT | Yes | `QUOTA-<rep-id>-YYYYQn`, e.g. `QUOTA-REP-000001-2026Q1` | Yes (PK) | Match rep ID and quarter in row |
| rep_id | TEXT | Yes | Rep ID | No (FK) | Must reference SalesRep |
| territory_id | TEXT | No | Territory ID | No (FK) | If present, must reference Territory |
| fiscal_quarter | TEXT | Yes | `2025Q1`–`2026Q4` | No | Match `^202[56]Q[1-4]$` |
| quota_amount | NUMERIC(14,2) | Yes | USD; greater than 0 | No | Finite positive amount; two decimals |
| currency_code | TEXT | Yes | `USD` | No | Must equal `USD` |
| quota_status | TEXT | Yes | `Draft`, `Active`, `Superseded` | No | Must be in enum |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## HistoricalBooking

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| booking_id | TEXT | Yes | `BOOK-` + 6 digits | Yes (PK) | Match `^BOOK-[0-9]{6}$` |
| account_id | TEXT | Yes | Account ID | No (FK) | Must reference Account |
| opportunity_id | TEXT | No | Opportunity ID | No (FK) | If present, opportunity must be Closed Won at booking recognition time |
| rep_id | TEXT | Yes | Rep ID | No (FK) | Must reference SalesRep; reflects credited rep at booking time |
| territory_id | TEXT | Yes | Territory ID | No (FK) | Must reference Territory; reflects territory at booking time |
| booking_date | DATE | Yes | Calendar date | No | Within dataset horizon; on/after opportunity close date when linked |
| booking_amount | NUMERIC(14,2) | Yes | USD; positive for recognition, negative for reversal | No | Nonzero finite amount; reversal references original booking through `reversal_of_booking_id` if that optional field is implemented |
| currency_code | TEXT | Yes | `USD` | No | Must equal `USD` |
| booking_type | TEXT | Yes | `New Business`, `Expansion`, `Renewal`, `Adjustment`, `Reversal` | No | Must be in enum; reversal must compensate a prior booking |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## ForecastSnapshot

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| forecast_id | TEXT | Yes | `FCST-YYYY-MM-DD-` + 3 digits | Yes (PK) | Match `^FCST-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}$`; date matches snapshot_date |
| snapshot_date | DATE | Yes | Calendar date | No | Within dataset horizon |
| period_start | DATE | Yes | Calendar date | No | On or before period_end |
| period_end | DATE | Yes | Calendar date | No | On or after period_start |
| forecast_type | TEXT | Yes | `Opportunity`, `Rep`, `Territory`, `Overall` | No | Dimension keys must match selected grain |
| opportunity_id | TEXT | No | Opportunity ID | No (FK) | Required for Opportunity grain; otherwise NULL |
| rep_id | TEXT | No | Rep ID | No (FK) | Required for Rep grain; otherwise NULL or used as grouping dimension only if grain is extended |
| territory_id | TEXT | No | Territory ID | No (FK) | Required for Territory grain; otherwise NULL or used as grouping dimension only if grain is extended |
| source_amount | NUMERIC(14,2) | Yes | USD | No | Sum of eligible source opportunity amounts at snapshot cutoff |
| weighted_amount | NUMERIC(14,2) | Yes | USD | No | Derived as source amount × applicable stage probability; never independently generated |
| actual_amount | NUMERIC(14,2) | No | USD | No | NULL until period closes; then derived from qualifying HistoricalBooking rows |
| model_version | TEXT | Yes | Non-empty version label | No | 1–40 chars; fixed for a run |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp; immutable snapshot creation time |

## RepTerritoryAssignment

| Field | Type | Required? | Allowed values / units | Unique? | Validation rule |
|---|---|---:|---|---:|---|
| assignment_id | TEXT | Yes | `RTA-` + 6 digits | Yes (PK) | Match `^RTA-[0-9]{6}$` |
| rep_id | TEXT | Yes | Rep ID | No (FK) | Must reference SalesRep |
| territory_id | TEXT | Yes | Territory ID | No (FK) | Must reference Territory |
| effective_from | DATE | Yes | Calendar date | No | Inclusive start; valid date |
| effective_to | DATE | No | Calendar date | No | Exclusive end; NULL means current; if present, strictly later than effective_from |
| assignment_type | TEXT | Yes | `Primary`, `Secondary` | No | Must be in enum; POC default policy permits one Primary territory at a time |
| created_at | TIMESTAMP | Yes | UTC timestamp | No | Valid ISO 8601 timestamp |

## Cross-table constraints

1. Every FK must resolve to an existing parent row.
2. An Opportunity's account, owner, and territory must exist. At creation, the rep must have an effective territory assignment consistent with the opportunity territory.
3. An Activity linked to an Opportunity must use the same Account as that Opportunity.
4. A StageHistory event must follow the permitted stage transition graph and sequence rules in `schema.md`.
5. Opportunity `current_stage`, `outcome`, `closed_date`, and any stored probability are derived from StageHistory and the stage catalogue; do not generate them independently.
6. A Won opportunity is eligible for booking recognition; a Lost opportunity cannot generate positive booking revenue.
7. A ForecastSnapshot's weighted amount must be reproducible from its source opportunity rows, their as-of stage, and the configured probability table.
8. The anomaly ground-truth file is not a table in this operational schema and must never be joined into validation inputs. It is used only for post-validation scoring/evaluation.
9. No source/history record is overwritten to represent a later state. Append a new event or compensating fact.
10. The dataset horizon is 2025-01-01 through 2026-12-31 inclusive; dates outside it are invalid unless a later scope explicitly extends the project.
