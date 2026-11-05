**# Project Assumptions and Derivation Rules**



**## 1. Scope and reproducibility**



**- All records are synthetic. No real customer, employee, territory, opportunity, or transaction data is used.**

**- Python 3.11+ is the documented runtime.**

**- The project uses pandas, numpy, pytest, and Python's standard-library sqlite3.**

**- The canonical generator is `src/generate\_data.py`.**

**- The fixed default seed is `20261022`.**

**- Supported scales:**

&#x20; **- Starter: 4 territories, 20 sales representatives, 20 accounts, 200 opportunities.**

&#x20; **- Full: 4 territories, 2,000 sales representatives, 2,000 accounts, 20,000 opportunities.**

**- Scale changes dataset volume, not the configured business rules.**

**- The Python function `generate\_dataset(scale, out, seed)` accepts a seed parameter. The command-line interface uses the fixed default seed.**

**- Run the generator from the repository root:**

&#x20; **- `python -m src.generate\_data --scale starter --out data/raw`**

&#x20; **- `python -m src.generate\_data --scale full --out data/raw`**

**- Generated IDs are deterministic for a given seed and generation configuration.**

**- Derived values are calculated from source records rather than independently sampled.**

**- Stage changes are stored as StageHistory events.**

**- Anomaly ground truth is stored separately under `data/anomalies/`.**



**## 2. Stage probabilities**



**The configured default probability is a deterministic lookup by stage:**



**| Stage | Probability |**

**|---|---:|**

**| Prospecting | 10% |**

**| Qualification | 25% |**

**| Proposal | 50% |**

**| Negotiation | 80% |**

**| Closed Won | 100% |**

**| Closed Lost | 0% |**



**Probabilities are proportions internally: `0.10`, `0.25`, `0.50`, `0.80`, `1.00`, and `0.00`.**



**They are stage-level defaults, not independently sampled opportunity probabilities. Forecast calculations obtain the probability associated with the opportunity's stage at the snapshot date.**



**The normal ForecastSnapshot CSV stores the stage ID, not a separate stage\_probability column. The anomaly dataset may add a deliberately corrupted stage\_probability field for anomaly testing.**



**## 3. Currency**



**- The project currency is USD.**

**- Monetary values are represented in USD with two decimal places.**

**- Generated currency codes are `USD`.**

**- No foreign-exchange conversion is performed.**

**- Mixed-currency records are invalid for the standard dataset and are deliberately introduced in the anomaly dataset.**



**## 4. Time horizon and seasonality**



**- The source-data horizon is January 1, 2025 through December 31, 2026.**

**- The dataset covers eight calendar quarters: 2025Q1 through 2026Q4.**

**- Calendar quarter mapping:**

&#x20; **- Q1: January 1–March 31**

&#x20; **- Q2: April 1–June 30**

&#x20; **- Q3: July 1–September 30**

&#x20; **- Q4: October 1–December 31**

**- The generator uses the following quarterly index:**



**| Quarter | Multiplier |**

**|---|---:|**

**| Q1 | 0.90 |**

**| Q2 | 0.95 |**

**| Q3 | 1.00 |**

**| Q4 | 1.15 |**



**- The index weights opportunity creation dates and adjusts generated opportunity amounts.**

**- These multipliers are synthetic project assumptions, not claims about real-world sales patterns.**

**- Seasonality is not applied again to derived weighted pipeline or booking totals.**



**## 5. Sales representatives and territory assignments**



**- Four synthetic territories are generated.**

**- Each representative has an initial effective-dated territory assignment.**

**- Approximately 20% of representatives are selected for a synthetic territory transfer.**

**- Assignment intervals use start-inclusive and end-exclusive dates.**

**- An opportunity receives the territory associated with its owner's assignment at opportunity creation.**

**- Opportunity territory is not automatically changed by later representative transfers.**

**- RepTerritoryAssignment is the implemented bridge between SalesRep and Territory.**



**## 6. Opportunity lifecycle and outcomes**



**The configured stage order is:**



**1. Prospecting**

**2. Qualification**

**3. Proposal**

**4. Negotiation**

**5. Closed Won or Closed Lost**



**Stage progression is generated using opportunity age and a deterministic synthetic representative activity tier.**



**The generator calculates:**



**- `age\_days`: days from opportunity creation to the dataset as-of date.**

**- `effective\_age`: opportunity age adjusted by the synthetic representative activity tier.**

**- `touch\_score`: a deterministic score based on generated activity-date count and representative activity tier.**



**The generated progression rules are:**



**- Effective age below 45 days: Prospecting.**

**- Effective age from 45 to below 110 days: Qualification is reached.**

**- Effective age from 110 to below 190 days: Proposal is reached.**

**- Effective age from 190 to below 285 days: Negotiation is reached.**

**- Effective age of 285 days or more: a terminal stage is generated.**

**- A terminal opportunity is Won when its touch score is at least 8.0 and effective age is at least 330 days.**

**- Otherwise, a terminal opportunity is Lost.**



**These are synthetic scenario rules, not trained or calibrated sales conversion probabilities.**



**StageHistory stores the generated lifecycle events. The Opportunity table's `current\_stage` and `outcome` represent the final generated state.**



**- Won opportunities have outcome `Won`.**

**- Lost opportunities have outcome `Lost`.**

**- Non-terminal opportunities have outcome `Open`.**

**- Closed opportunities receive a `closed\_date` derived from the final stage event.**

**- Open opportunities have a NULL `closed\_date`.**



**## 7. Activities**



**- Activities are generated for opportunities.**

**- Each opportunity receives between two and eight generated activity-date candidates; duplicate dates are removed.**

**- Generated activity types are Call, Email, and Meeting.**

**- Generated activity outcomes are `Completed`.**

**- Activity records link to Opportunity and SalesRep.**

**- Account-level-only activities are not generated in the current implementation.**

**- Activity IDs use the format `ACT-<opportunity-id>-NNN`.**



**The synthetic touch score uses the number of generated activity dates and the representative activity tier. It does not independently classify each activity outcome to decide the opportunity outcome.**



**## 8. Stale opportunities and snapshot slippage**



**- Forecast snapshots are generated at monthly month-end dates from January 31, 2025 through December 31, 2026.**

**- Snapshot state is reconstructed using StageHistory events on or before the snapshot date.**

**- Activity dates after the snapshot cutoff are not used to calculate the snapshot's last activity date.**

**- `stale\_days` is calculated from the last activity date as of the snapshot, or from opportunity creation when no activity is available.**

**- `is\_stale` is true when `stale\_days >= 30`.**

**- The normal ForecastSnapshot table stores `last\_activity\_date`, `stale\_days`, and `is\_stale`.**



**For forecast slippage:**



**- The snapshot generator calculates a synthetic push count from stale days.**

**- For each complete 30-day period beyond the initial 30-day threshold, it pushes the expected close date by another 30 days.**

**- The snapshot's expected close date is the original opportunity expected close date plus the calculated push days.**

**- This is a derived snapshot value. The current implementation does not store a separate append-only close-date revision event table.**



**## 9. Quotas and historical bookings**



**- Quotas are generated for each sales representative and each quarter from 2025Q1 through 2026Q4.**

**- The generated quota amount is USD 250,000.00 per representative per quarter.**

**- HistoricalBooking records are generated for Won opportunities only.**

**- A booking links to its opportunity, account, and representative.**

**- Booking amount is derived from the Won opportunity amount.**

**- Booking date is derived from the opportunity close date.**

**- Lost and Open opportunities do not generate positive historical booking records.**

**- Booking IDs use the format `BOOK-<opportunity-id>`.**



**## 10. Forecast derivation**



**- ForecastSnapshot is an opportunity-level snapshot table.**

**- Each row represents one eligible opportunity at one snapshot date.**

**- The snapshot stores the opportunity ID, stage ID, amount, expected close date, last activity date, stale days, and stale flag.**

**- Snapshot stage is reconstructed from the latest StageHistory event on or before the snapshot date.**

**- Closed Won and Closed Lost opportunities are excluded from the open pipeline snapshots.**

**- Weighted expected revenue is calculated as:**



&#x20; **`weighted\_amount = amount × stage\_probability`**



**- Stage probability is looked up from the Stage reference table using the stage recorded in the snapshot.**

**- Rep, territory, and overall pipeline totals are derived by aggregating opportunity-level records and their related dimensions. They are not separate snapshot grains in the generated ForecastSnapshot CSV.**

**- Historical actuals are derived from HistoricalBooking records, not from forecast values.**

**- Snapshot reconstruction must not use future StageHistory or Activity events.**



**## 11. Forecast scenarios**



**- Baseline expected revenue is `amount × stage\_probability`.**

**- The pessimistic scenario applies a `0.75` multiplier to baseline stage probability and then a separate `0.85` multiplier to expected revenue.**

**- Adjusted probability is bounded between 0 and 1.**

**- The optimistic scenario applies a `1.20` multiplier to baseline stage probability, capped at `1.00`.**

**- Scenario rows retain the same underlying snapshot opportunity, amount, date, stage, and territory information.**

**- Scenario summaries aggregate scenario detail by scenario, calendar quarter, territory, and stage.**

**- Scenario outputs are deterministic what-if adjustments. They are not statistical confidence intervals or calibrated probability estimates.**



**## 12. Validation and anomaly ground truth**



**- The clean generated dataset is validated independently from the deliberately corrupted anomaly dataset.**

**- Standard validation covers primary keys, foreign keys, required values, enumerations, date rules, arithmetic, and business constraints.**

**- The anomaly dataset contains five labelled issue types:**

&#x20; **- Close date before creation.**

&#x20; **- Mixed currency.**

&#x20; **- Stage probability mismatch.**

&#x20; **- Future information leakage in a historical snapshot.**

&#x20; **- Duplicate opportunity in a snapshot.**

**- Ground-truth labels are stored separately from the source tables.**

**- Ground truth is used to score anomaly detection after validation, not as an input to the detection rules.**

**- The anomaly-only `stage\_probability` field is not part of the normal ForecastSnapshot CSV schema.**



**## 13. Historical snapshot revenue evaluation**



**The evaluation module compares expected revenue from historical opportunity snapshots with later booked revenue.**



**- It evaluates opportunities appearing in a snapshot that later have a valid closed outcome and close date.**

**- Booking records are joined by opportunity.**

**- Multiple booking records for one opportunity are summed before actual booked revenue is calculated.**

**- Closed opportunities with no booking records are treated as zero booked revenue.**

**- Reported measures include expected revenue, actual booked revenue, signed error, absolute error, WAPE, and signed bias.**

**- Positive signed error means over-forecast; negative signed error means under-forecast.**

**- Results are grouped by snapshot-to-close horizon and dimensions such as territory, product, and representative.**

**- Horizon buckets are 0–30, 31–60, 61–90, 91–180, and 181+ days.**

**- This is a historical snapshot evaluation, not a live forecast or causal assessment.**

**- It does not score opportunities missing from a snapshot, open opportunities without a valid close date, or unrecorded bookings.**

**- No currency conversion is performed.**



**## 14. Provenance and lawful use**



**- All project data is synthetic.**

**- No external datasets or personal data are used to generate or populate the datasets.**

**- The project is intended for development, testing, and demonstration with synthetic data only.**

**- Real customer, employee, or prospect data must not be introduced into generated datasets.**
