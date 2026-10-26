from datetime import datetime, timezone


def calculate_risk(probability: float) -> str:
    if probability < 30:
        return "HIGH"
    elif probability <= 50:
        return "MEDIUM"
    else:
        return "LOW"


def is_deal_overdue(expected_close_date: datetime | None) -> bool:
    if expected_close_date is None:
        return False

    if expected_close_date.tzinfo is None:
        expected_close_date = expected_close_date.replace(tzinfo=timezone.utc)

    return expected_close_date < datetime.now(timezone.utc)


def calculate_overall_risk(
    probability: float,
    is_overdue: bool,
    activity_status: str,
    has_expected_close_date: bool = True,
) -> tuple[str, list[str]]:
    risk_reasons = []
    risk_signal_count = 0

    if probability < 30:
        risk_reasons.append("Low closing probability")
        risk_signal_count += 1

    if is_overdue:
        risk_reasons.append("Expected close date has passed")
        risk_signal_count += 1
    elif not has_expected_close_date:
        risk_reasons.append("Expected close date is not set")

    normalized_activity_status = activity_status.upper()
    if normalized_activity_status in {"STALE", "INACTIVE", "NO_ACTIVITY"}:
        if normalized_activity_status == "NO_ACTIVITY":
            risk_reasons.append("No customer activity recorded")
        elif normalized_activity_status == "STALE":
            risk_reasons.append("Customer activity is stale")
        else:
            risk_reasons.append("No recent customer activity")
        risk_signal_count += 1

    if risk_signal_count >= 2:
        overall_risk_level = "HIGH"
    elif risk_signal_count == 1:
        overall_risk_level = "MEDIUM"
    else:
        overall_risk_level = "LOW"

    return overall_risk_level, risk_reasons