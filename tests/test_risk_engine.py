import unittest
from datetime import date, datetime, timezone

from app.engine.risk_engine import (
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


if __name__ == "__main__":
    unittest.main()
