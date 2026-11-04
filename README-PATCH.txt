# Generator implementation patch

Copy `src/generate_data.py` and `tests/test_generate_data.py` into the matching paths in your repository.

Install dependencies:
```bash
python -m pip install -r requirements.txt
```

Run:
```bash
python -m src.generate_data --scale starter --out data/raw
python -m pytest -q
```

The generator uses seed `20261022`, emits CSVs for Territory, Stage, SalesRep,
Account, RepTerritoryAssignment, Opportunity, and StageHistory, and writes
deterministically. Seasonality affects opportunity creation-date sampling and
source amount only, consistent with `docs/assumptions.md`.
