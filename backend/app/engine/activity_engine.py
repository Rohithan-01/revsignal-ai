from datetime import datetime, timedelta, timezone

ACTIVITY_FUTURE_SKEW_TOLERANCE = timedelta(minutes=5)


def normalize_activity_timestamp(
    activity_date: datetime,
    now: datetime | None = None,
) -> datetime:
    if activity_date.tzinfo is None or activity_date.utcoffset() is None:
        raise ValueError("activity_date must include a timezone offset")

    normalized_date = activity_date.astimezone(timezone.utc)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current_time = current_time.astimezone(timezone.utc)

    if normalized_date > current_time + ACTIVITY_FUTURE_SKEW_TOLERANCE:
        raise ValueError(
            "activity_date cannot be more than five minutes in the future"
        )

    return normalized_date


def calculate_days_since_last_activity(
    activity_date: datetime | None,
    now: datetime | None = None,
) -> int | None:

    if activity_date is None:
        return None

    if activity_date.tzinfo is None:
        activity_date = activity_date.replace(tzinfo=timezone.utc)
    else:
        activity_date = activity_date.astimezone(timezone.utc)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    difference = current_time.astimezone(timezone.utc) - activity_date

    if difference < timedelta(0):
        if -difference <= ACTIVITY_FUTURE_SKEW_TOLERANCE:
            return 0
        return None

    return difference.days

def get_latest_activity_date(
    activity_dates: list[datetime],
) -> datetime | None:

    if not activity_dates:
        return None

    normalized_dates = [
        activity_date.replace(tzinfo=timezone.utc)
        if activity_date.tzinfo is None
        else activity_date.astimezone(timezone.utc)
        for activity_date in activity_dates
    ]
    return max(normalized_dates)

def calculate_activity_signal(
    activity_dates: list[datetime],
    now: datetime | None = None,
) -> int | None:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current_time = current_time.astimezone(timezone.utc)

    eligible_activity_dates = []
    for activity_date in activity_dates:
        if activity_date.tzinfo is None:
            activity_date = activity_date.replace(tzinfo=timezone.utc)
        else:
            activity_date = activity_date.astimezone(timezone.utc)

        if activity_date <= current_time + ACTIVITY_FUTURE_SKEW_TOLERANCE:
            eligible_activity_dates.append(activity_date)

    latest_activity_date = max(eligible_activity_dates, default=None)
    return calculate_days_since_last_activity(latest_activity_date, current_time)

def get_activity_status(
    days_since_last_activity: int | None,
) -> str:

    if days_since_last_activity is None:
        return "NO_ACTIVITY"

    if days_since_last_activity <= 3:
        return "ACTIVE"

    if days_since_last_activity <= 7:
        return "STALE"

    return "INACTIVE"