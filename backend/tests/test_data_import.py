from datetime import date
from io import BytesIO
from pathlib import Path

import pytest

from backend.app.data_import import (
    import_csv_records,
    normalize_record,
    synthetic_sample_rows,
)


def test_normalize_record_handles_aliases_and_missing_optional_values():
    row = {
        "Deal ID": "D-200",
        "Account": "Demo Account",
        "Amount": 90000,
        "Sales Stage": "Proposal",
        "Status": "Open",
        "Expected Close": "2026-10-30",
    }

    result = normalize_record(row)

    assert result["deal_id"] == "D-200"
    assert result["account_name"] == "Demo Account"
    assert result["deal_value"] == 90000.0
    assert result["stage"] == "Proposal"
    assert result["status"] == "Open" or result["status"] == "open"
    assert result["expected_close_date"] == date(2026, 10, 30)
    assert result["probability"] is None
    assert result["probability_is_known"] is False


@pytest.mark.parametrize("probability", [25, 40, 50, 75])
def test_normalize_record_marks_explicit_probability_as_known(probability):
    result = normalize_record(
        {
            "deal_id": "D-210",
            "account_name": "Probability Account",
            "deal_value": 90000,
            "stage": "Proposal",
            "probability": probability,
        }
    )

    assert result["probability"] == float(probability)
    assert result["probability_is_known"] is True


def test_normalize_record_rejects_invalid_probability():
    with pytest.raises(ValueError, match="probability must be a number"):
        normalize_record(
            {
                "deal_id": "D-211",
                "account_name": "Invalid Probability",
                "deal_value": 90000,
                "stage": "Proposal",
                "probability": "unknown",
            }
        )


def test_import_csv_records_reads_uploaded_csv_without_a_temp_file():
    uploaded = BytesIO(
        b"deal_id,account_name,deal_value,stage,status\n"
        b"D-201,Example Account,125000,Proposal,open\n"
    )

    records = import_csv_records(uploaded)

    assert len(records) == 1
    assert records[0]["deal_id"] == "D-201"
    assert records[0]["deal_value"] == 125000
    assert records[0]["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert records[0]["expected_close_date"] is None


def test_synthetic_sample_rows_are_loaded_and_use_calendar_dates():
    rows = synthetic_sample_rows()

    assert rows
    assert all(
        row["expected_close_date"] is None
        or isinstance(row["expected_close_date"], date)
        for row in rows
    )


def test_sample_crm_csv_imports_all_rows_with_typed_values():
    sample_file = Path(__file__).resolve().parents[2] / "data" / "sample_crm.csv"

    records = import_csv_records(BytesIO(sample_file.read_bytes()))

    assert len(records) == 8
    assert records[0]["deal_id"] == "D-105"
    assert records[0]["account_name"] == "Northwind Labs"
    assert records[0]["created_date"] == date(2026, 6, 1)
    assert records[0]["expected_close_date"] == date(2026, 10, 25)
    assert records[0]["activity_count"] == 5
    assert isinstance(records[0]["activity_count"], int)
    assert records[0]["probability"] == 50
    assert records[0]["probability_is_known"] is False
    assert {
        record["account_name"]: record["deal_id"]
        for record in records
    } == {
        "Northwind Labs": "D-105",
        "Harbor Retail": "D-106",
        "Apex Manufacturing": "D-107",
        "Meridian Health": "D-108",
        "Velora Systems": "D-109",
        "Summit Legal": "D-110",
        "BluePeak Financial": "D-111",
        "Greenline Logistics": "D-112",
    }
    assert {record["deal_id"] for record in records} == {
        f"D-{number}" for number in range(105, 113)
    }


def test_frontend_and_backend_sample_crm_files_match():
    repository_root = Path(__file__).resolve().parents[2]
    backend_sample = repository_root / "data" / "sample_crm.csv"
    frontend_sample = repository_root / "frontend" / "public" / "sample_crm.csv"

    assert frontend_sample.read_bytes() == backend_sample.read_bytes()


def test_import_csv_records_reports_missing_required_columns():
    uploaded = BytesIO(
        b"deal_id,account_name,deal_value,stage\n"
        b"D-202,Example Account,125000,Proposal\n"
    )

    with pytest.raises(ValueError, match="Missing: status"):
        import_csv_records(uploaded)


def test_import_csv_records_reports_invalid_deal_value_with_row_number():
    uploaded = BytesIO(
        b"deal_id,account_name,deal_value,stage,status\n"
        b"D-203,Example Account,not-a-number,Proposal,open\n"
    )

    with pytest.raises(ValueError, match="row 2: deal_value must be a non-negative number"):
        import_csv_records(uploaded)


def test_import_csv_records_rejects_duplicate_ids_in_the_same_file():
    uploaded = BytesIO(
        b"deal_id,account_name,deal_value,stage,status\n"
        b"D-204,First Account,125000,Proposal,open\n"
        b"D-204,Second Account,150000,Negotiation,open\n"
    )

    with pytest.raises(ValueError, match="Duplicate deal_id 'D-204' on CSV row 3"):
        import_csv_records(uploaded)


@pytest.mark.parametrize("deal_id", ["legacy-1", "D-0", "D-01", "CRM-22"])
def test_normalize_record_rejects_noncanonical_deal_ids(deal_id):
    with pytest.raises(ValueError, match="canonical format D-<positive integer>"):
        normalize_record(
            {
                "deal_id": deal_id,
                "account_name": "Invalid Deal ID",
                "deal_value": 1000,
                "stage": "Proposal",
            }
        )


@pytest.mark.parametrize(
    ("header", "row", "error"),
    [
        (
            "deal_id,account_name,deal_value,stage,status,expected_close_date\n",
            "D-205,Example,10,Proposal,open,not-a-date\n",
            "row 2: date values must use",
        ),
        (
            "deal_id,account_name,deal_value,stage,status,activity_count\n",
            "D-206,Example,10,Proposal,open,1.5\n",
            "row 2: activity_count must be a non-negative integer",
        ),
        (
            "deal_id,account_name,deal_value,stage,status,meeting_count\n",
            "D-207,Example,10,Proposal,open,-1\n",
            "row 2: meeting_count must be a non-negative integer",
        ),
        (
            "deal_id,account_name,deal_value,stage,status,email_count\n",
            "D-209,Example,10,Proposal,open,unknown\n",
            "row 2: email_count must be a non-negative integer",
        ),
    ],
)
def test_import_csv_records_rejects_invalid_optional_values(header, row, error):
    with pytest.raises(ValueError, match=error):
        import_csv_records(BytesIO((header + row).encode("utf-8")))


def test_import_csv_records_rejects_malformed_rows():
    uploaded = BytesIO(
        b"deal_id,account_name,deal_value,stage,status\n"
        b"D-208,Example,10,Proposal,open,extra-column\n"
    )

    with pytest.raises(ValueError, match="Malformed CSV row 2"):
        import_csv_records(uploaded)


def test_probability_migration_only_adds_unknown_provenance_flag():
    migration_file = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "manual"
        / "0003_track_probability_provenance.sql"
    )
    migration = migration_file.read_text(encoding="utf-8").lower()

    assert "add column probability_is_known boolean not null default false" in migration
    assert "update public.deals" not in migration
    assert "set probability =" not in migration


def test_deal_id_migration_and_rollback_include_confirmed_mapping_and_guards():
    migration_directory = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "manual"
    )
    migration = (
        migration_directory / "0004_standardize_deal_ids.sql"
    ).read_text(encoding="utf-8")
    rollback = (
        migration_directory / "rollback_0004_standardize_deal_ids.sql"
    ).read_text(encoding="utf-8")

    mappings = [
        (1, "legacy-1", "D-101", "TechNova Solutions"),
        (2, "legacy-2", "D-102", "Zenith Technologies"),
        (3, "legacy-3", "D-103", "BlueWave Solutions"),
        (4, "legacy-4", "D-104", "PixelCore Systems"),
        (5, "D-1001", "D-105", "Northwind Labs"),
        (6, "D-1002", "D-106", "Harbor Retail"),
        (7, "D-1003", "D-107", "Apex Manufacturing"),
        (8, "D-1004", "D-108", "Meridian Health"),
        (9, "D-1005", "D-109", "Velora Systems"),
        (10, "D-1006", "D-110", "Summit Legal"),
        (11, "D-1007", "D-111", "BluePeak Financial"),
        (12, "D-1008", "D-112", "Greenline Logistics"),
    ]
    for internal_id, old_id, new_id, company in mappings:
        assert f"({internal_id}, '{old_id}', '{new_id}', '{company}')" in migration
        assert f"({internal_id}, '{new_id}', '{old_id}', '{company}')" in rollback

    for script in (migration, rollback):
        lowered = script.lower()
        assert "begin;" in lowered
        assert "commit;" in lowered
        assert "lock table public.deals in access exclusive mode" in lowered
        assert "select count(*)" in lowered
        assert "from public.deals" in lowered
        assert "is distinct from" in lowered
        assert "d.id not between 1 and 12" in lowered
        assert "set deal_id =" in lowered
        assert "set company =" not in lowered
        assert "set id =" not in lowered
