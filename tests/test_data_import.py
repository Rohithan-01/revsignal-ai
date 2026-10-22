from io import BytesIO

import pytest

from app.data_import import import_csv_records, normalize_record


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
    assert result["expected_close_date"] is not None


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
