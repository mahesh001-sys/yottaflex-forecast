# Data Schema

## 1. Scope and conventions

- All project records are synthetic and generated deterministically.
- The implemented schema describes the actual CSV outputs produced by `src/generate_data.py`.
- The dataset uses USD for monetary values.
- Date fields use ISO 8601 `YYYY-MM-DD` format.
- Monetary values are represented as numeric decimal values with two decimal places.
- Probabilities are numeric values between `0.0` and `1.0`.
- Primary keys are deterministic string identifiers.
- Foreign keys reference identifiers in the related parent tables.
- `NULL` represents an optional or unavailable value.
- `StageHistory` records opportunity stage changes as separate history rows.
- Forecast snapshots are opportunity-level records reconstructed using information available on each snapshot date.
- The fixed default generator seed is `20261022`.

### Dataset scales

| Scale | Territories | Sales representatives | Accounts | Opportunities |
|---|---:|---:|---:|---:|
| Starter | 4 | 20 | 20 | 200 |
| Full | 4 | 2,000 | 2,000 | 20,000 |

The generator supports a seed argument through its Python function. The command-line interface uses the documented default seed.

## 2. Canonical identifier formats

| Entity | Primary key | Format |
|---|---|---|
| SalesRep | `rep_id` | `REP-000001` |
| Territory | `territory_id` | `TER-0001` |
| Account | `account_id` | `ACC-000001` |
| Opportunity | `opportunity_id` | `OPP-2026-000001` |
| Stage | `stage_id` | `STAGE-001` |
| StageHistory | `stage_history_id` | `STG-<opportunity-id>-001` |
| Activity | `activity_id` | `ACT-<opportunity-id>-001` |
| Quota | `quota_id` | `QUOTA-<rep-id>-2025Q1` |
| HistoricalBooking | `booking_id` | `BOOK-<opportunity-id>` |
| ForecastSnapshot | `forecast_snapshot_id` | `FCST-2025-01-31-001` |
| RepTerritoryAssignment | `assignment_id` | `RTA-000001` |

Sequences are generated deterministically. The date and quarter portions identify the relevant creation cohort, snapshot date, or fiscal quarter.

## 3. Implemented tables

### 3.1 SalesRep

**Purpose:** Stores synthetic sales representative master records.

- Primary key: `rep_id`
- Foreign keys: None

| Field | Description |
|---|---|
| `rep_id` | Unique sales representative identifier |
| `rep_name` | Synthetic representative name |
| `email` | Synthetic email address |
| `hire_date` | Representative hire date |
| `employment_status` | Employment status |
| `created_at` | Synthetic record creation timestamp |

Generated employment status: `Active`.

### 3.2 Territory

**Purpose:** Defines sales territories and their geographic classification.

- Primary key: `territory_id`
- Foreign keys: None

| Field | Description |
|---|---|
| `territory_id` | Unique territory identifier |
| `territory_name` | Territory name |
| `region` | Geographic region |
| `country_code` | Country code |
| `status` | Territory status |
| `created_at` | Synthetic record creation timestamp |

Generated regions: `North`, `South`, `East`, `West`.

Generated territory status: `Active`.

### 3.3 Account

**Purpose:** Stores synthetic customer and prospect organizations.

- Primary key: `account_id`
- Foreign key: `territory_id` → `Territory.territory_id`

| Field | Description |
|---|---|
| `account_id` | Unique account identifier |
| `account_name` | Synthetic account name |
| `industry` | Account industry |
| `account_status` | Prospect or customer status |
| `territory_id` | Assigned territory |
| `created_at` | Synthetic record creation timestamp |

Generated industries include Technology, Healthcare, Manufacturing, Retail, Finance, Education, Logistics, and Telecommunications.

Generated account statuses: `Prospect`, `Customer`.

Accounts linked to a won opportunity can be marked as customers.

### 3.4 Opportunity

**Purpose:** Represents a synthetic sales opportunity and its current derived state.

- Primary key: `opportunity_id`
- Foreign keys:
  - `account_id` → `Account.account_id`
  - `owner_rep_id` → `SalesRep.rep_id`
  - `territory_id` → `Territory.territory_id`
  - `source_opportunity_id` → `Opportunity.opportunity_id` (nullable self-reference)

| Field | Description |
|---|---|
| `opportunity_id` | Unique opportunity identifier |
| `opportunity_name` | Synthetic opportunity name |
| `account_id` | Associated account |
| `owner_rep_id` | Owning sales representative |
| `territory_id` | Territory assigned at opportunity creation |
| `source_opportunity_id` | Optional source opportunity reference |
| `created_date` | Opportunity creation date |
| `expected_close_date` | Expected close date |
| `amount` | Opportunity amount in USD |
| `currency_code` | Currency code |
| `product` | Associated product |
| `current_stage` | Current/final stage name |
| `closed_date` | Closing date; nullable for open opportunities |
| `outcome` | Opportunity outcome |

Generated products: `Platform`, `Analytics`, `Automation`, `Integration`, `Support`.

Generated outcomes: `Open`, `Won`, `Lost`.

The `current_stage` field stores the stage name, not the stage identifier. Stage identifiers and transition history are stored in `Stage` and `StageHistory`.

`source_opportunity_id` is nullable and is currently generated as NULL.

### 3.5 Stage

**Purpose:** Defines the controlled sales pipeline stages.

- Primary key: `stage_id`
- Foreign keys: None

| Field | Description |
|---|---|
| `stage_id` | Unique stage identifier |
| `stage_name` | Stage name |
| `stage_order` | Pipeline order |
| `default_probability` | Default probability for the stage |
| `is_closed_stage` | Whether the stage is terminal |

The six configured stages are:

| Stage ID | Stage name | Order | Probability | Closed stage |
|---|---|---:|---:|---|
| STAGE-001 | Prospecting | 1 | 0.10 | No |
| STAGE-002 | Qualification | 2 | 0.25 | No |
| STAGE-003 | Proposal | 3 | 0.50 | No |
| STAGE-004 | Negotiation | 4 | 0.80 | No |
| STAGE-005 | Closed Won | 5 | 1.00 | Yes |
| STAGE-006 | Closed Lost | 6 | 0.00 | Yes |

### 3.6 StageHistory

**Purpose:** Stores the sequence of opportunity stage transitions.

- Primary key: `stage_history_id`
- Foreign keys:
  - `opportunity_id` → `Opportunity.opportunity_id`
  - `from_stage_id` → `Stage.stage_id` (nullable for the initial event)
  - `to_stage_id` → `Stage.stage_id`
  - `changed_by_rep_id` → `SalesRep.rep_id`

| Field | Description |
|---|---|
| `stage_history_id` | Unique stage history event identifier |
| `opportunity_id` | Associated opportunity |
| `from_stage_id` | Previous stage; NULL for the initial event |
| `to_stage_id` | New stage |
| `changed_by_rep_id` | Representative associated with the change |
| `changed_at` | Stage transition timestamp |
| `reason` | Synthetic transition reason |
| `event_sequence` | Sequence number within the opportunity history |

Each opportunity has an ordered stage history.

The initial event has a NULL `from_stage_id`. Subsequent events record the previous and new stage identifiers.

Stage history is used to reconstruct the opportunity's stage as of a historical cutoff date.

### 3.7 Activity

**Purpose:** Stores synthetic sales activities associated with opportunities and representatives.

- Primary key: `activity_id`
- Foreign keys:
  - `opportunity_id` → `Opportunity.opportunity_id`
  - `rep_id` → `SalesRep.rep_id`

| Field | Description |
|---|---|
| `activity_id` | Unique activity identifier |
| `opportunity_id` | Associated opportunity |
| `rep_id` | Representative performing the activity |
| `activity_type` | Activity category |
| `activity_date` | Activity date |
| `subject` | Synthetic activity subject |
| `outcome` | Activity outcome |

Generated activity types: `Call`, `Email`, `Meeting`.

Generated activity outcome: `Completed`.

Activities in the implemented dataset are linked to opportunities. The schema does not currently implement account-only activities.

### 3.8 Quota

**Purpose:** Stores quarterly sales targets for representatives.

- Primary key: `quota_id`
- Foreign key: `rep_id` → `SalesRep.rep_id`

| Field | Description |
|---|---|
| `quota_id` | Unique quota identifier |
| `rep_id` | Associated sales representative |
| `fiscal_quarter` | Fiscal quarter |
| `quota_amount` | Quarterly target amount in USD |
| `currency_code` | Currency code |

The generator creates one quota per representative for each quarter from 2025Q1 through 2026Q4.

Generated quota amount: USD 250,000.00.

There is no territory foreign key in the implemented quota table.

### 3.9 HistoricalBooking

**Purpose:** Stores booked revenue associated with won opportunities.

- Primary key: `booking_id`
- Foreign keys:
  - `opportunity_id` → `Opportunity.opportunity_id`
  - `account_id` → `Account.account_id`
  - `rep_id` → `SalesRep.rep_id`

| Field | Description |
|---|---|
| `booking_id` | Unique booking identifier |
| `opportunity_id` | Associated won opportunity |
| `account_id` | Associated account |
| `rep_id` | Representative associated with the booking |
| `booking_date` | Booking recognition date |
| `booking_amount` | Booked amount in USD |
| `currency_code` | Currency code |

The generator creates a booking for each won opportunity.

The booking amount equals the opportunity amount, and the booking date equals the opportunity's closing date.

There are no non-opportunity adjustment or reversal records in the current implementation.

### 3.10 ForecastSnapshot

**Purpose:** Stores monthly opportunity-level forecast state as of a historical snapshot date.

- Primary key: `forecast_snapshot_id`
- Foreign keys:
  - `opportunity_id` → `Opportunity.opportunity_id`

| Field | Description |
|---|---|
| `forecast_snapshot_id` | Unique forecast snapshot identifier |
| `snapshot_date` | Snapshot cutoff date |
| `opportunity_id` | Associated opportunity |
| `stage_id` | Stage identifier as of the snapshot date |
| `amount` | Opportunity amount in USD |
| `expected_close_date` | Expected close date as of the snapshot |
| `last_activity_date` | Latest activity date available by the snapshot date |
| `stale_days` | Days since the last activity, or creation date if no activity exists |
| `is_stale` | Whether the opportunity is considered stale |

The generator creates monthly month-end snapshots from January 2025 through December 2026, covering 24 snapshot dates and eight quarters.

Snapshot reconstruction follows these rules:

1. Only stage history events dated on or before the snapshot date are considered.
2. The latest eligible stage event determines the snapshot stage.
3. Closed Won and Closed Lost opportunities are excluded from open pipeline snapshots.
4. Only activities dated on or before the snapshot date are considered.
5. `stale_days` is calculated from the last eligible activity date, or opportunity creation date when no activity exists.
6. An opportunity is stale when `stale_days >= 30`.
7. Expected close dates are pushed according to the documented stale-opportunity slippage rule.

The implemented snapshot grain is one row per opportunity per applicable snapshot date. It does not contain representative-level, territory-level, or overall aggregate snapshot rows.

The normal forecast snapshot CSV does not contain a `stage_probability` column. The anomaly dataset adds that field to a deliberately corrupted record for testing.

### 3.11 RepTerritoryAssignment

**Purpose:** Represents effective-dated sales representative territory assignments.

- Primary key: `assignment_id`
- Foreign keys:
  - `rep_id` → `SalesRep.rep_id`
  - `territory_id` → `Territory.territory_id`

| Field | Description |
|---|---|
| `assignment_id` | Unique assignment identifier |
| `rep_id` | Assigned representative |
| `territory_id` | Assigned territory |
| `effective_from` | Assignment start date, inclusive |
| `effective_to` | Assignment end date, exclusive; nullable |

The initial assignment starts on 2025-01-01.

A subset of representatives receives a territory transfer during the generated period. The old assignment ends on the transfer date, and the new assignment starts on that same date.

The effective-dated assignment table provides the many-to-many relationship between representatives and territories over time.

## 4. Relationship and cardinality summary

| Parent | Child | Cardinality | Implemented relationship |
|---|---|---|---|
| Territory | Account | 1:N | Each generated account has one territory |
| Territory | Opportunity | 1:N | Each opportunity has one territory |
| SalesRep | Opportunity | 1:N | Each opportunity has one owner |
| Account | Opportunity | 1:N | Each opportunity belongs to one account |
| Opportunity | StageHistory | 1:N | Each opportunity has ordered stage events |
| Stage | StageHistory | 1:N | A stage can appear in many transition events |
| Opportunity | Activity | 1:N | Activities are linked to opportunities |
| SalesRep | Activity | 1:N | Each activity has one representative |
| SalesRep | Quota | 1:N | Each representative has quarterly quotas |
| Opportunity | HistoricalBooking | 1:0..1 | Won opportunities have one booking |
| Account | HistoricalBooking | 1:N | Each booking references one account |
| SalesRep | HistoricalBooking | 1:N | Each booking references one representative |
| Opportunity | ForecastSnapshot | 1:N | Each opportunity can appear in multiple snapshots |
| SalesRep | RepTerritoryAssignment | 1:N | A representative can have assignment history |
| Territory | RepTerritoryAssignment | 1:N | A territory can have multiple representative assignments |

SalesRep and Territory have a many-to-many relationship over time through `RepTerritoryAssignment`.

## 5. Temporal and lifecycle rules

### Effective-dated territory assignments

- `effective_from` is inclusive.
- `effective_to` is exclusive.
- An assignment is active on date `d` when:

  `effective_from <= d AND (effective_to IS NULL OR d < effective_to)`

- The old territory assignment ends on the transfer date.
- The new assignment begins on the same date.
- Opportunity territory is assigned using the representative's territory assignment effective on the opportunity creation date.

### Opportunity stage lifecycle

The configured stage progression is:

```text
Prospecting
    |
    v
Qualification
    |
    v
Proposal
    |
    v
Negotiation
   / \
  v   v
Closed Won   Closed Lost