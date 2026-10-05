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