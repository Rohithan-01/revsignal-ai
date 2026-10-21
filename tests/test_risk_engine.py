from app.risk_engine import analyze_deal


def test_high_risk_is_identified_for_overdue_low_activity_deal():
    record = {
        "deal_id": "D-100",
        "account_name": "Test Account",
        "deal_value": 50000,
        "stage": "Proposal",
        "status": "open",
        "created_date": "2026-01-01",
        "expected_close_date": "2026-10-01",
        "last_activity_date": "2026-08-15",
        "activity_count": 1,
        "meeting_count": 0,
        "email_count": 0,
        "stakeholder_count": 1,
    }

    result = analyze_deal(record)

    assert result["risk_level"] in {"HIGH", "MEDIUM"}
    assert result["risk_score"] >= 60
    assert any("activity" in reason.lower() or "close date" in reason.lower() for reason in result["risk_reasons"])
    assert result["recommended_action"]


def test_low_risk_deal_has_balanced_signals():
    record = {
        "deal_id": "D-101",
        "account_name": "Healthy Account",
        "deal_value": 220000,
        "stage": "Qualified",
        "status": "open",
        "created_date": "2026-08-01",
        "expected_close_date": "2026-11-15",
        "last_activity_date": "2026-10-16",
        "activity_count": 8,
        "meeting_count": 3,
        "email_count": 8,
        "stakeholder_count": 5,
    }

    result = analyze_deal(record)

    assert result["risk_level"] in {"LOW", "MEDIUM"}
    assert result["risk_score"] < 70
