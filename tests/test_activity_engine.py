import unittest
from datetime import datetime, timedelta, timezone

from app.engine.activity_engine import (
    ACTIVITY_FUTURE_SKEW_TOLERANCE,
    calculate_activity_signal,
    calculate_days_since_last_activity,
    normalize_activity_timestamp,
    get_activity_status,
)


class GetActivityStatusTests(unittest.TestCase):
    def test_no_activity_returns_no_activity(self):
        self.assertEqual(get_activity_status(None), "NO_ACTIVITY")

    def test_zero_days_returns_active(self):
        self.assertEqual(get_activity_status(0), "ACTIVE")

    def test_three_day_boundary_returns_active(self):
        self.assertEqual(get_activity_status(3), "ACTIVE")

    def test_four_days_returns_stale(self):
        self.assertEqual(get_activity_status(4), "STALE")

    def test_seven_day_boundary_returns_stale(self):
        self.assertEqual(get_activity_status(7), "STALE")

    def test_eight_days_returns_inactive(self):
        self.assertEqual(get_activity_status(8), "INACTIVE")

    def test_empty_activity_timestamps_have_no_signal(self):
        self.assertIsNone(calculate_activity_signal([]))

    def test_activity_timestamp_is_normalized_to_utc(self):
        fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        timestamp = datetime(
            2026, 1, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )

        self.assertEqual(
            normalize_activity_timestamp(timestamp, now=fixed_now),
            fixed_now,
        )

    def test_naive_activity_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone offset"):
            normalize_activity_timestamp(datetime(2026, 1, 1, 12, 0))

    def test_future_skew_tolerance_is_exactly_five_minutes(self):
        fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        within_tolerance = fixed_now + ACTIVITY_FUTURE_SKEW_TOLERANCE
        beyond_tolerance = within_tolerance + timedelta(microseconds=1)

        self.assertEqual(
            normalize_activity_timestamp(within_tolerance, now=fixed_now),
            within_tolerance,
        )
        with self.assertRaisesRegex(ValueError, "five minutes"):
            normalize_activity_timestamp(beyond_tolerance, now=fixed_now)

    def test_future_activity_within_tolerance_has_zero_age(self):
        fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        days = calculate_days_since_last_activity(
            fixed_now + timedelta(minutes=5),
            now=fixed_now,
        )

        self.assertEqual(days, 0)

    def test_historical_future_activity_is_ignored_for_assessment(self):
        fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        future_activity = fixed_now + timedelta(hours=2)

        self.assertIsNone(
            calculate_days_since_last_activity(future_activity, now=fixed_now)
        )
        self.assertIsNone(
            calculate_activity_signal([future_activity], now=fixed_now)
        )

    def test_activity_assessment_uses_latest_eligible_timestamp(self):
        fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        older_activity = fixed_now - timedelta(days=4)
        future_activity = fixed_now + timedelta(hours=2)

        self.assertEqual(
            calculate_activity_signal(
                [older_activity, future_activity],
                now=fixed_now,
            ),
            4,
        )

    def test_activity_age_uses_elapsed_twenty_four_hour_periods(self):
        fixed_now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)

        self.assertEqual(
            calculate_days_since_last_activity(
                fixed_now - timedelta(days=3, hours=23),
                now=fixed_now,
            ),
            3,
        )
        self.assertEqual(
            calculate_days_since_last_activity(
                fixed_now - timedelta(days=4),
                now=fixed_now,
            ),
            4,
        )


if __name__ == "__main__":
    unittest.main()
