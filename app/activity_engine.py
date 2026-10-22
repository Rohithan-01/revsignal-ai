from datetime import datetime, timezone
from typing import Optional


def calculate_days_since_last_activity(
    activity_date: Optional[datetime],
) -> Optional[int]:

    if activity_date is None:
        return None

    if activity_date.tzinfo is None:
        activity_date = activity_date.replace(tzinfo=timezone.utc)

    difference = datetime.now(timezone.utc) - activity_date

    return difference.days

def get_latest_activity_date(
    activity_dates: list[datetime],
) -> Optional[datetime]:

    if not activity_dates:
        return None

    return max(activity_dates)

def calculate_activity_signal(
    activity_dates: list[datetime],
) -> Optional[int]:

    latest_activity_date = get_latest_activity_date(activity_dates)

    return calculate_days_since_last_activity(
        latest_activity_date
    )

def get_activity_status(
    days_since_last_activity: Optional[int],
) -> str:

    if days_since_last_activity is None:
        return "NO_ACTIVITY"

    if days_since_last_activity <= 3:
        return "ACTIVE"

    if days_since_last_activity <= 7:
        return "STALE"

    return "INACTIVE"