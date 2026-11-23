
import unittest
from datetime import date, datetime, timedelta, timezone

from backend.app.engine.risk_engine import (
    calculate_overall_risk,
    calculate_risk,
    is_deal_overdue,
)


class CalculateOverallRiskTests(unittest.TestCase):
    def test_all_three_signals_produce_high_risk(self):
        risk_level, reasons = calculate_overall_risk(
            probability=25,
            is_overdue=True,
            activity_status="INACTIVE",
        )

        self.assertEqual(risk_level, "HIGH")
        self.assertEqual(
            reasons,
            [
                "Low closing probability",
                "Expected close date has passed",
                "No recent customer activity",
            ],
        )

    def test_two_signals_produce_high_risk(self):
        risk_level, _ = calculate_overall_risk(
            probability=25,
            is_overdue=False,
            activity_status="STALE",
        )

        self.assertEqual(risk_level, "HIGH")

    def test_one_signal_produces_medium_risk(self):
        risk_level, reasons = calculate_overall_risk(
            probability=40,
            is_overdue=True,
            activity_status="ACTIVE",
        )

        self.assertEqual(risk_level, "MEDIUM")
        self.assertEqual(reasons, ["Expected close date has passed"])

    def test_low_probability_alone_produces_medium_risk(self):
        risk_level, reasons = calculate_overall_risk(
            probability=25,
            is_overdue=False,
            activity_status="ACTIVE",
        )

        self.assertEqual(risk_level, "MEDIUM")
        self.assertEqual(reasons, ["Low closing probability"])

    def test_no_signals_produce_low_risk(self):
        risk_level, reasons = calculate_overall_risk(
            probability=50,
            is_overdue=False,
            activity_status="ACTIVE",
        )

        self.assertEqual(risk_level, "LOW")
        self.assertEqual(reasons, [])

    def test_no_activity_counts_as_a_risk_signal(self):
        risk_level, reasons = calculate_overall_risk(
            probability=70,
            is_overdue=False,
            activity_status="NO_ACTIVITY",
        )

        self.assertEqual(risk_level, "MEDIUM")
        self.assertEqual(reasons, ["No customer activity recorded"])

    def test_missing_close_date_is_reported_but_not_counted_as_risk(self):
        risk_level, reasons = calculate_overall_risk(
            probability=70,
            is_overdue=False,
            activity_status="ACTIVE",
            has_expected_close_date=False,
        )

        self.assertEqual(risk_level, "LOW")
        self.assertEqual(reasons, ["Expected close date is not set"])

    def test_probability_thresholds(self):
        self.assertEqual(calculate_risk(29.99), "HIGH")
        self.assertEqual(calculate_risk(30), "MEDIUM")
        self.assertEqual(calculate_risk(50), "MEDIUM")
        self.assertEqual(calculate_risk(50.01), "LOW")

    def test_close_date_is_not_overdue_until_business_day_ends(self):
        close_date = date(2026, 11, 10)

        before_end_of_close_date = datetime(
            2026, 11, 10, 18, 29, 59, tzinfo=timezone.utc
        )
        start_of_next_local_date = datetime(
            2026, 11, 10, 18, 30, tzinfo=timezone.utc
        )

        self.assertFalse(
            is_deal_overdue(close_date, "Asia/Kolkata", before_end_of_close_date)
        )
        self.assertTrue(
            is_deal_overdue(close_date, "Asia/Kolkata", start_of_next_local_date)
        )

    def test_overdue_uses_business_timezone_on_dst_transition(self):
        close_date = date(2026, 3, 8)

        before_end_of_close_date = datetime(
            2026, 3, 9, 3, 59, tzinfo=timezone.utc
        )
        start_of_next_local_date = datetime(
            2026, 3, 9, 4, 0, tzinfo=timezone.utc
        )

        self.assertFalse(
            is_deal_overdue(
                close_date,
                "America/New_York",
                before_end_of_close_date,
            )
        )
        self.assertTrue(
            is_deal_overdue(
                close_date,
                "America/New_York",
                start_of_next_local_date,
            )
        )

    def test_overdue_rejects_datetime_close_values_and_naive_now(self):
        with self.assertRaises(ValueError):
            is_deal_overdue(datetime(2026, 11, 10))
        with self.assertRaises(ValueError):
            is_deal_overdue(date(2026, 11, 10), now=datetime(2026, 11, 11))

    def test_missing_close_date_is_not_overdue(self):
        self.assertFalse(is_deal_overdue(None))


from backend.app.risk_engine import analyze_deal, calculate_crm_risk_level


def _balanced_deal_record(**overrides):
    record = {
        "deal_id": "D-300",
        "account_name": "Probability Account",
        "deal_value": 50000,
        "stage": "Proposal",
        "status": "open",
        "created_date": date.today(),
        "expected_close_date": date.today() + timedelta(days=60),
        "last_activity_date": date.today(),
        "activity_count": 5,
        "meeting_count": 2,
        "email_count": 5,
        "stakeholder_count": 3,
    }
    record.update(overrides)
    return record


def test_known_probability_levels_combine_with_score_based_risk():
    expected_levels = {25: "HIGH", 40: "MEDIUM", 50: "MEDIUM", 75: "LOW"}
    for probability, expected_level in expected_levels.items():
        result = analyze_deal(
            _balanced_deal_record(
                probability=probability,
                probability_is_known=True,
            )
        )
        assert result["risk_level"] == expected_level
        assert result["probability_is_known"] is True


def test_omitted_and_explicit_default_probability_have_distinct_provenance():
    unknown = analyze_deal(_balanced_deal_record())
    explicit_default = analyze_deal(
        _balanced_deal_record(probability=50, probability_is_known=True)
    )

    assert unknown["probability"] == explicit_default["probability"] == 50
    assert unknown["probability_is_known"] is False
    assert explicit_default["probability_is_known"] is True
    assert unknown["risk_level"] == "LOW"
    assert explicit_default["risk_level"] == "MEDIUM"


def test_unknown_probability_does_not_change_risk_or_add_probability_reason():
    unknown = analyze_deal(
        _balanced_deal_record(probability=25, probability_is_known=False)
    )

    assert unknown["risk_level"] == "LOW"
    assert not any("probability" in reason.lower() for reason in unknown["risk_reasons"])


def test_probability_only_raises_score_risk_and_adds_reason_when_known():
    assert calculate_crm_risk_level(40, 25, True) == (
        "HIGH",
        "Closing probability is 25%, raising risk to HIGH.",
    )
    assert calculate_crm_risk_level(40, 25, False) == ("MEDIUM", None)
    assert calculate_crm_risk_level(80, 25, True) == ("HIGH", None)


def test_missing_activity_and_close_date_recommendations_remain_actionable():
    missing_activity = analyze_deal(
        _balanced_deal_record(last_activity_date=None)
    )
    overdue = analyze_deal(
        _balanced_deal_record(expected_close_date=date.today() - timedelta(days=1))
    )
    approaching_close = analyze_deal(
        _balanced_deal_record(expected_close_date=date.today() + timedelta(days=10))
    )

    assert "customer follow-up" in missing_activity["recommended_action"].lower()
    assert "close date" in overdue["recommended_action"].lower()
    assert "close plan" in approaching_close["recommended_action"].lower()


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


if __name__ == "__main__":
    unittest.main()
