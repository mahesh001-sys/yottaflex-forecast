# Data Schema

## 1. Conventions

- The system uses synthetic sales data only.
- All timestamps are stored in UTC using ISO 8601 format; date-only business-effective fields use `DATE`.
- Monetary amounts are `DECIMAL(14,2)` in USD. Probabilities and rates are `DECIMAL(5,4)` in the range `0.0000`–`1.0000`.
- Surrogate identifiers are deterministic, zero-padded strings. IDs are generated in stable sort order from the fixed synthetic-data seed (`20261022`), not from runtime randomness. The canonical formats are listed below and must be used consistently by the generator and exports.
- Historical state changes are append-only. Current state is derived from the latest applicable event/history row; prior rows are not updated or deleted.
- `effective_from` is inclusive and `effective_to` is exclusive. A NULL `effective_to` means the assignment remains open-ended.
- Every entity has `created_at` and, where relevant, source/effective timestamps. These are synthetic timestamps.
- The table definitions below are a logical relational schema. SQLite implementations may represent `DATE`, `TIMESTAMP`, and `DECIMAL` as validated `TEXT`/`INTEGER`/`NUMERIC` columns because SQLite has dynamic typing.

## 1A. Canonical ID formats

IDs are deterministic, stable, and zero-padded. The generator must assign them in stable source-record order; rerunning with the same seed and scale must reproduce the same IDs.

| Entity | ID format |
|---|---|
| SalesRep | `REP-000001` |
| Territory | `TER-0001` |
| Account | `ACC-000001` |
| Opportunity | `OPP-2026-000001` |
| StageHistory event | `STG-<opportunity-id>-001` |
| Activity linked to an opportunity | `ACT-<opportunity-id>-0001` |
| Account-level Activity without an opportunity | `ACT-<account-id>-0001` |
| Quota | `QUOTA-<rep-id>-2026Q1` |
| Opportunity-linked HistoricalBooking | `BKG-<opportunity-id>-001` |
| Non-opportunity booking adjustment | `BKG-ADJ-000001` |
| ForecastSnapshot | `FCST-2026-01-31-001` |

The literal date/quarter segments identify the relevant cohort, quarter, or snapshot date. Per-parent sequences start at `001` (or `0001` for Activity) and increase without reuse. The account-level Activity and adjustment formats cover the schema's explicitly optional opportunity foreign keys.

## 2. Tables, primary keys and foreign keys

### SalesRep
- **PK:** `rep_id` (`REP-000001` format).
- **FKs:** none.
- **Purpose:** synthetic sales representative master record.
- **Important fields:** `rep_name`, `email`, `hire_date`, `employment_status`, `created_at`.
- **Lifecycle:** `Active` → `Inactive`; reactivation, if modelled, is a new status event rather than rewriting history.

### Territory
- **PK:** `territory_id` (`TER-0001` format).
- **FKs:** none.
- **Purpose:** sales geography or coverage unit.
- **Important fields:** `territory_name`, `region`, `country_code`, `created_at`.
- **Lifecycle:** `Active` → `Inactive`. Territory identity is stable; changes in coverage are represented through assignments.

### Account
- **PK:** `account_id` (`ACC-000001` format).
- **FKs:** optional `territory_id` → `Territory.territory_id` (current/default territory attribution only).
- **Purpose:** synthetic customer/prospect organization.
- **Important fields:** `account_name`, `industry`, `account_status`, `created_at`.
- **Lifecycle:** `Prospect` → `Customer` or `Disqualified`; account conversion is derived from related opportunity outcomes, not independently randomized.

### Opportunity
- **PK:** `opportunity_id` (`OPP-2026-000001` format; year segment is the opportunity creation cohort year).
- **FKs:** `account_id` → `Account.account_id` (required); `owner_rep_id` → `SalesRep.rep_id` (required); `territory_id` → `Territory.territory_id` (required); optional `source_opportunity_id` → `Opportunity.opportunity_id` for explicitly modelled renewals/expansions.
- **Purpose:** sales pursuit and its current derived state.
- **Important fields:** `opportunity_name`, `created_date`, `expected_close_date`, `amount`, `currency_code`, `current_stage`, `closed_date`, `outcome`.
- **Lifecycle:** `Prospecting` → `Qualification` → `Proposal` → `Negotiation` → `Closed Won` or `Closed Lost`. A deal may remain in its current open stage, or move forward one stage at a time. Reopening a closed deal is not an allowed transition in this POC; create a new linked opportunity if needed.
- **Outcome:** `Open` while in an open stage; `Won` only in `Closed Won`; `Lost` only in `Closed Lost`. The outcome is derived from stage history under documented transition rules.

### Stage
- **PK:** `stage_id` (controlled catalogue ID, `STAGE-001` format).
- **FKs:** none.
- **Purpose:** controlled stage catalogue.
- **Important fields:** `stage_name`, `stage_order`, `default_probability`, `is_closed_stage`.
- **Lifecycle:** reference data; the six configured stage names and probabilities are specified in `assumptions.md`.

### StageHistory
- **PK:** `stage_history_id` (`STG-<opportunity-id>-001` format; the final sequence is zero-padded to three digits and increments per opportunity).
- **FKs:** `opportunity_id` → `Opportunity.opportunity_id`; `stage_id` → `Stage.stage_id`; `changed_by_rep_id` → `SalesRep.rep_id` (optional).
- **Purpose:** append-only record of every opportunity stage transition.
- **Important fields:** `from_stage_id` (optional FK → `Stage.stage_id`), `to_stage_id` (required FK → `Stage.stage_id`), `changed_at`, `reason`, `event_sequence`.
- **Cardinality:** one Opportunity has 1:N StageHistory rows; each Stage can be referenced by 1:N history rows as a source and/or destination.
- **Validation:** first event has NULL `from_stage_id` and `to_stage_id = Prospecting`; subsequent event's `from_stage_id` must equal the previous event's `to_stage_id`; transition must be allowed; `event_sequence` increases strictly per opportunity. No history row is overwritten.

### Activity
- **PK:** `activity_id` (`ACT-<opportunity-id>-0001` format for opportunity-linked activities; sequence is zero-padded to four digits and increments per opportunity. For account-level activities without an opportunity, use `ACT-<account-id>-0001`).
- **FKs:** `opportunity_id` → `Opportunity.opportunity_id` (optional); `account_id` → `Account.account_id` (required); `rep_id` → `SalesRep.rep_id` (required).
- **Purpose:** synthetic sales touchpoint such as a call, email, meeting, or demo.
- **Important fields:** `activity_type`, `occurred_at`, `outcome`, `notes`.
- **Cardinality:** Account 1:N Activity; SalesRep 1:N Activity; Opportunity 0..1:N Activity (an activity can be account-level without being linked to an opportunity).
- **Validation:** if `opportunity_id` is present, its `account_id` must match the activity's `account_id`.

### Quota
- **PK:** `quota_id` (`QUOTA-<rep-id>-2026Q1` format).
- **FKs:** `rep_id` → `SalesRep.rep_id` (required); optional `territory_id` → `Territory.territory_id`.
- **Purpose:** quarterly sales target for a representative, optionally scoped to a territory.
- **Important fields:** `fiscal_quarter`, `quota_amount`, `currency_code`, `created_at`.
- **Cardinality:** SalesRep 1:N Quota; Territory 0..1:N Quota.
- **Uniqueness:** one quota per `(rep_id, fiscal_quarter)`; if territory-scoped quotas are later required, revise the uniqueness rule to `(rep_id, territory_id, fiscal_quarter)` explicitly rather than silently allowing duplicates.

### HistoricalBooking
- **PK:** `booking_id` (`BKG-<opportunity-id>-001` format for opportunity-linked bookings; sequence is zero-padded to three digits and increments per opportunity. For non-opportunity adjustments, use `BKG-ADJ-000001`).
- **FKs:** `account_id` → `Account.account_id`; `opportunity_id` → `Opportunity.opportunity_id` (optional); `rep_id` → `SalesRep.rep_id`; `territory_id` → `Territory.territory_id`.
- **Purpose:** immutable synthetic booked-revenue fact at the date it was recognized.
- **Important fields:** `booking_date`, `booking_amount`, `currency_code`, `booking_type`.
- **Cardinality:** Account 1:N HistoricalBooking; SalesRep 1:N HistoricalBooking; Territory 1:N HistoricalBooking; Opportunity 0..1:N HistoricalBooking.
- **Validation:** a booking linked to an opportunity must reference a `Closed Won` opportunity and its amount/date must satisfy the booking recognition rule. Corrections are represented by compensating booking rows, not updates/deletes.

### ForecastSnapshot
- **PK:** `forecast_id` (`FCST-2026-01-31-001` format; date segment is the snapshot date).
- **FKs:** `rep_id` → `SalesRep.rep_id` (optional for aggregate snapshots); `territory_id` → `Territory.territory_id` (optional); `opportunity_id` → `Opportunity.opportunity_id` (optional for aggregate snapshots).
- **Purpose:** immutable point-in-time forecast output.
- **Important fields:** `snapshot_date`, `period_start`, `period_end`, `forecast_type`, `source_amount`, `weighted_amount`, `actual_amount`, `model_version`, `created_at`.
- **Cardinality:** Rep/Territory/Opportunity each 0..1:N ForecastSnapshot. A snapshot row may be opportunity-level, rep-level, territory-level, or overall; the grain is identified by `forecast_type` and nullable dimension keys.
- **Validation:** `weighted_amount` is derived from source opportunity amount and the stage probability known at the snapshot cutoff; `actual_amount` is populated only when the period has closed and qualifying booking facts exist. Snapshots are append-only.

### RepTerritoryAssignment
- **PK:** `assignment_id` (`RTA-000001` format).
- **FKs:** `rep_id` → `SalesRep.rep_id`; `territory_id` → `Territory.territory_id`.
- **Purpose:** bridge table tracking which reps cover which territories over time.
- **Required effective dates:** `effective_from` (inclusive); `effective_to` (exclusive, nullable for current assignment).
- **Cardinality:** SalesRep N:M Territory through RepTerritoryAssignment. Each Rep and each Territory has 1:N assignment rows over time.
- **Validation:** `effective_to` must be later than `effective_from`; assignments for the same rep/territory cannot overlap; a rep cannot have overlapping active assignments to conflicting territories unless an explicit multi-territory policy is adopted. Historical rows are closed by appending an assignment-end event or by maintaining an immutable assignment record plus a separate event log; do not silently rewrite past coverage.

## 3. Relationships and cardinality summary

| Parent | Child / bridge | Cardinality | Optionality |
|---|---|---|---|
| Territory | Account | 1:N | Account territory is optional |
| Account | Opportunity | 1:N | Each opportunity requires one account |
| SalesRep | Opportunity | 1:N | Each opportunity requires one owner |
| Territory | Opportunity | 1:N | Each opportunity requires one territory |
| Opportunity | StageHistory | 1:N | Every opportunity should have an initial stage event |
| Stage | StageHistory (from/to) | 1:N | `from_stage_id` is NULL only for initial event |
| Account | Activity | 1:N | Required |
| SalesRep | Activity | 1:N | Required |
| Opportunity | Activity | 1:N | Activity's opportunity link is optional |
| SalesRep | Quota | 1:N | Required |
| Territory | Quota | 1:N | Quota territory is optional |
| Account | HistoricalBooking | 1:N | Required |
| SalesRep | HistoricalBooking | 1:N | Required |
| Territory | HistoricalBooking | 1:N | Required |
| Opportunity | HistoricalBooking | 1:N | Optional for non-opportunity adjustments |
| SalesRep | Territory | N:M | Implemented by RepTerritoryAssignment |
| SalesRep | ForecastSnapshot | 1:N | Snapshot rep dimension optional |
| Territory | ForecastSnapshot | 1:N | Snapshot territory dimension optional |
| Opportunity | ForecastSnapshot | 1:N | Snapshot opportunity dimension optional |

## 4. Effective dating and temporal rules

1. `RepTerritoryAssignment.effective_from` is inclusive; `effective_to` is exclusive. For a date `d`, an assignment is active when `effective_from <= d` and (`effective_to IS NULL` or `d < effective_to`).
2. Two assignments for the same rep must not overlap when the project uses a single-primary-territory policy. A territory transfer is represented by ending the old interval and starting a new interval on the transfer date.
3. Opportunity ownership/territory at a historical point is resolved from the assignment effective on that date. The opportunity's stored `territory_id` is its assigned territory at creation unless a separately recorded reassignment event is introduced.
4. StageHistory is event time, not merely a current-state field. The latest valid event at or before a cutoff determines the stage at that cutoff.
5. ForecastSnapshot stores a point-in-time result. Later stage changes, bookings, or territory changes must not alter an existing snapshot.

## 5. Lifecycle states and allowed stage transitions

### Opportunity stage graph

```text
[Prospecting] -> [Qualification] -> [Proposal] -> [Negotiation]
      |                 |                |              |
      +-----------------+----------------+--------------+--> [Closed Lost]
                                                       |
                                                       +--> [Closed Won]
```

More precisely, allowed transitions are:

- Initial state: NULL → Prospecting.
- Prospecting → Qualification or Closed Lost.
- Qualification → Proposal or Closed Lost.
- Proposal → Negotiation or Closed Lost.
- Negotiation → Closed Won or Closed Lost.
- Same-stage events are not stage transitions; record activities or notes instead.
- Backward transitions, skipping stages, reopening closed deals, and Closed Won ↔ Closed Lost are disallowed in this POC.

`current_stage`, `outcome`, `closed_date`, and current stage probability on Opportunity are derived from StageHistory. They must not be independently randomized.

### Other entity states

- SalesRep: `Active`, `Inactive`.
- Territory: `Active`, `Inactive`.
- Account: `Prospect`, `Customer`, `Disqualified`.
- Opportunity outcome: `Open`, `Won`, `Lost` (derived from stage).
- Activity status: `Planned`, `Completed`, `Cancelled` if an activity status is needed; activity type and outcome are separate controlled fields.
- Quota: `Draft`, `Active`, `Superseded` if quota lifecycle is needed. A revised quota is a new version/event, not an overwrite.
- HistoricalBooking: `Recognized`, `Reversed`; reversal uses a compensating row.
- ForecastSnapshot: `Final` (immutable once written); reruns create a new snapshot ID/version.

## 6. Text ER diagram

```text
SalesRep 1 -----< Opportunity >----- 1 Account
    |                   |                |
    |                   |                +-----< Activity >----- 1 SalesRep
    |                   |
    |                   +-----< StageHistory >----- 1 Stage (to_stage)
    |                                  |
    |                                  +---------- 0..1 Stage (from_stage)
    |
    +-----< Quota >----- 0..1 Territory
    |
    +-----< HistoricalBooking >----- 1 Account
    |               |               |
    |               +---------------+----- 1 Territory
    |
    +-----< RepTerritoryAssignment >----- 1 Territory
    |
    +-----< ForecastSnapshot >----- 0..1 Territory
                         |
                         +---------- 0..1 Opportunity

Territory 1 -----< Account (optional account territory)
Territory 1 -----< Opportunity
Opportunity 1 ---< Activity (optional activity opportunity)
Opportunity 1 ---< HistoricalBooking (optional booking opportunity)
Opportunity 1 ---< ForecastSnapshot (optional snapshot opportunity)
```

`RepTerritoryAssignment` is the associative entity that resolves the SalesRep–Territory N:M relationship and preserves effective-dated coverage history.


## Provenance and lawful use

- All records produced by this project are synthetic and are created solely for proof-of-concept development, testing, and demonstration.
- No external datasets, customer records, employee records, personal data, or other real-world source data were used to create the project data.
- The canonical generator is invoked with `python -m src.generate_data --scale starter` or `python -m src.generate_data --scale full`.
- The fixed generator seed is `20261022`; the selected scale changes dataset volume only and must not change the documented business rules.
- The generator command and seed must be recorded in the run manifest so each generated dataset can be reproduced and audited.
