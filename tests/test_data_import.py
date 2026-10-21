from app.data_import import normalize_record


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
