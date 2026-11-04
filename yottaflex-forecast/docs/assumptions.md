# Project Assumptions and Derivation Rules

## 1. Scope and reproducibility

- All records are synthetic. No real customer, employee, territory, opportunity, or transaction data is used.
- Python 3.11+ is the runtime. The project uses pandas, numpy, pytest, and Python's standard-library `sqlite3`.
- The fixed random seed is `20261022`. The project has one canonical data generator with `--scale starter|full`; scale changes volume, not business rules.
- Every module is runnable as `python -m src.<module>`.
- Generated IDs are deterministic and zero-padded. Required examples include `REP-000001`, `OPP-2026-000001`, `STG-<opportunity-id>-001`, `QUOTA-<rep-id>-2026Q1`, and `FCST-2026-01-31-001`.
- Derived fields are computed from source records. They are not generated independently.
- State changes are append-only events. Existing history is never overwritten.
- Anomaly ground truth is stored separately under `data/anomalies/` and is excluded from validation inputs. It may be used only after validation to score anomaly-detection performance.

## 2. Stage probabilities

The configured default probability is a deterministic lookup by stage:

| Stage | Probability |
|---|---:|
| Prospecting | 10% |
| Qualification | 25% |
| Proposal | 50% |
| Negotiation | 80% |
| Closed Won | 100% |
| Closed Lost | 0% |

Probabilities are proportions internally (`0.10`, `0.25`, `0.50`, `0.80`, `1.00`, `0.00`). They are not sampled per opportunity. The stage probability used in a historical forecast is the probability associated with the stage at the snapshot cutoff date.

## 3. Currency

- The project currency is **USD**.
- Every monetary amount is represented in USD with two decimal places.
- `currency_code` must be `USD`.
- No foreign-exchange conversion is performed. If multi-currency support is added later, it must be an explicit extension with dated exchange-rate source records.

## 4. Time horizon

- The dataset covers eight quarters: **2025Q1 through 2026Q4**, inclusive.
- Calendar quarter mapping:
  - Q1: January 1–March 31
  - Q2: April 1–June 30
  - Q3: July 1–September 30
  - Q4: October 1–December 31
- Dates and timestamps are synthetic and bounded by this horizon unless a test intentionally creates an out-of-range invalid record.
- Quotas are defined by rep and fiscal quarter. Forecast snapshots use explicit snapshot dates and forecast periods within the horizon.

## 5. Won and lost outcomes

- Outcomes are determined only by StageHistory and the allowed transition graph.
- An opportunity becomes **Won** only when its stage transitions to `Closed Won`; it becomes **Lost** only when its stage transitions to `Closed Lost`.
- A Won/Lost opportunity receives a `closed_date` derived from the timestamp/date of the terminal stage event.
- An open opportunity has outcome `Open` and a NULL `closed_date`.
- No independent random outcome label is assigned. The synthetic generator may use deterministic scenario rules to decide which valid transition event occurs, but the stored outcome must always be reproducible from the event history.
- A positive HistoricalBooking may be recognized only for a Won opportunity. A Lost opportunity cannot produce positive booking revenue.
- Account conversion to `Customer` is derived from qualifying Won booking/outcome evidence; it is not randomly assigned.

## 6. Slippage

- Slippage means an opportunity's expected close date moves later than its previous expected close date or passes its expected close date without closing.
- Every close-date change is represented as an append-only opportunity event (or a dedicated append-only date-change event table if implemented); do not overwrite the original expected close date.
- For a simple derived metric, `slipped_days = max(0, actual_or_as_of_date - expected_close_date)` for an open deal that remains open after its expected close date. For explicit date revisions, calculate the shift from the prior expected close date and retain each revision.
- A deal closed after its expected close date is late by the positive day difference between closed_date and expected_close_date.
- A deal that closes on or before its expected close date has zero close-date slippage.
- Do not infer slippage from random labels.

## 7. Stale deals

- An opportunity is stale when it remains open and has had no qualifying sales Activity for more than 30 calendar days as of the evaluation/snapshot date.
- Qualifying activities are `Call`, `Email`, `Meeting`, and `Demo` with `activity_status = Completed`; `Task` does not reset the engagement clock unless explicitly enabled in a later rule version.
- `last_activity_at` is derived as the maximum qualifying Activity timestamp for that opportunity (or its account, if account-level activities are explicitly included by the chosen implementation rule).
- `stale_days = as_of_date - last_activity_date`. If there is no qualifying activity, use opportunity `created_date` as the baseline.
- Stale status is derived at query/snapshot time and is not an independently generated or manually assigned field.

## 8. Seasonality

- Seasonality affects synthetic source demand/booking patterns, not labels or outcomes directly.
- Use a documented deterministic quarterly index applied to a base volume/amount before records are created. Suggested initial index (multipliers): Q1 `0.90`, Q2 `0.95`, Q3 `1.00`, Q4 `1.15`.
- The index is a configurable project assumption, not a claim about real-world sales. It must be fixed for a generator version and recorded in the manifest.
- Apply seasonality to source opportunity creation volume and/or source deal amount according to a documented generator choice. Do not apply it a second time to derived weighted pipeline, bookings, or forecast outputs.
- Won/lost outcomes remain determined by lifecycle rules; seasonality must not directly flip an opportunity's outcome.

## 9. Forecast derivation

- Opportunity weighted amount at a snapshot is `amount × stage_probability_as_of_snapshot`.
- Rep/territory/overall pipeline forecasts are sums of eligible opportunity-level weighted amounts within the relevant dimensions and forecast period.
- Closed Won opportunities have 100% stage probability; Closed Lost opportunities have 0%.
- Actuals are derived from HistoricalBooking facts within the forecast period, not from generated forecast values.
- A snapshot is immutable. Re-running a forecast creates a new snapshot ID/version rather than editing a previous snapshot.

## 10. Ambiguities resolved for this schema

- `Stage` is a controlled reference table. `StageHistory` stores transitions; `Opportunity.current_stage` and `outcome` are cached/derived values only.
- `RepTerritoryAssignment` is the effective-dated N:M bridge. Intervals are start-inclusive/end-exclusive.
- Opportunity territory is the territory assigned at opportunity creation unless a separate append-only reassignment event is added in a future schema revision.
- `HistoricalBooking` may optionally link to an Opportunity to support non-opportunity adjustments, but ordinary new-business/expansion/renewal bookings should link to the Won opportunity that generated them.
- ForecastSnapshot permits nullable dimension keys to support opportunity-, rep-, territory-, and overall-level snapshots. The implementation must enforce a consistent grain for each `forecast_type`.
- The exact starter/full row counts are intentionally not fixed in these docs; they belong in the generator specification/manifest so they can evolve without changing business semantics.
