import csv

from src.check_business_rules import (
    check_date_ordering,
    check_duplicate_snapshot_opportunities,
    check_enums,
    check_lifecycle,
    check_snapshot_time_consistency,
    check_weighted_pipeline,
)


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_enum_check_detects_invalid_value(tmp_path, capsys):
    write_csv(
        tmp_path / "account.csv",
        ["account_status"],
        [{"account_status": "NotAStatus"}],
    )

    violations = check_enums(tmp_path)
    output = capsys.readouterr().out

    assert violations > 0
    assert "FAIL | allowed enums" in output


def test_date_ordering_detects_close_date_before_created_date(
    tmp_path, capsys
):
    write_csv(
        tmp_path / "opportunity.csv",
        ["created_date", "expected_close_date"],
        [{
            "created_date": "2026-05-10",
            "expected_close_date": "2026-05-09",
        }],
    )

    violations = check_date_ordering(tmp_path)
    output = capsys.readouterr().out

    assert violations == 1
    assert "FAIL | date ordering" in output


def test_lifecycle_detects_invalid_stage_transition(tmp_path, capsys):
    write_csv(
        tmp_path / "stage.csv",
        ["stage_id", "stage_name"],
        [
            {"stage_id": "S1", "stage_name": "Prospecting"},
            {"stage_id": "S2", "stage_name": "Negotiation"},
        ],
    )
    write_csv(
        tmp_path / "stage_history.csv",
        [
            "opportunity_id",
            "changed_at",
            "from_stage_id",
            "to_stage_id",
        ],
        [
            {
                "opportunity_id": "O1",
                "changed_at": "2026-01-01T10:00:00",
                "from_stage_id": "",
                "to_stage_id": "S1",
            },
            {
                "opportunity_id": "O1",
                "changed_at": "2026-01-02T10:00:00",
                "from_stage_id": "S1",
                "to_stage_id": "S2",
            },
        ],
    )

    violations = check_lifecycle(tmp_path)
    output = capsys.readouterr().out

    assert violations > 0
    assert "FAIL | StageHistory lifecycle" in output


def test_weighted_pipeline_detects_reconciliation_mismatch(
    tmp_path, capsys
):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    write_csv(
        processed_dir / "forecast_detail.csv",
        [
            "quarter",
            "territory_id",
            "stage_id",
            "amount",
            "stage_probability",
            "expected_revenue",
        ],
        [{
            "quarter": "2026Q1",
            "territory_id": "T1",
            "stage_id": "S1",
            "amount": "100",
            "stage_probability": "0.5",
            "expected_revenue": "50",
        }],
    )
    write_csv(
        processed_dir / "forecast_summary.csv",
        [
            "quarter",
            "territory_id",
            "stage_id",
            "total_weighted_pipeline",
        ],
        [{
            "quarter": "2026Q1",
            "territory_id": "T1",
            "stage_id": "S1",
            "total_weighted_pipeline": "60",
        }],
    )

    violations = check_weighted_pipeline(raw_dir)
    output = capsys.readouterr().out

    assert violations > 0
    assert "FAIL | weighted pipeline reconciliation" in output


def test_snapshot_time_consistency_detects_future_activity(
    tmp_path, capsys
):
    write_csv(
        tmp_path / "forecast_snapshot.csv",
        [
            "snapshot_date",
            "last_activity_date",
            "opportunity_id",
            "stage_id",
        ],
        [{
            "snapshot_date": "2026-01-01",
            "last_activity_date": "2026-01-02",
            "opportunity_id": "O1",
            "stage_id": "S1",
        }],
    )
    write_csv(
        tmp_path / "stage_history.csv",
        [
            "opportunity_id",
            "changed_at",
            "to_stage_id",
        ],
        [],
    )

    violations = check_snapshot_time_consistency(tmp_path)
    output = capsys.readouterr().out

    assert violations > 0
    assert "FAIL | snapshot time-consistency" in output


def test_duplicate_snapshot_check_detects_duplicate_opportunity(
    tmp_path, capsys
):
    write_csv(
        tmp_path / "forecast_snapshot.csv",
        ["snapshot_date", "opportunity_id"],
        [
            {"snapshot_date": "2026-01-01", "opportunity_id": "O1"},
            {"snapshot_date": "2026-01-01", "opportunity_id": "O1"},
        ],
    )

    violations = check_duplicate_snapshot_opportunities(tmp_path)
    output = capsys.readouterr().out

    assert violations == 1
    assert "FAIL | no duplicate opportunity within snapshot" in output