def generate_recommendation(risk_level: str, is_overdue: bool) -> str:
    if risk_level == "HIGH" and is_overdue:
        return "Review deal immediately"

    if risk_level == "HIGH" and not is_overdue:
        return "Closely monitor and follow up"

    if risk_level == "MEDIUM" and is_overdue:
        return "Follow up with the customer"

    if risk_level == "MEDIUM" and not is_overdue:
        return "Schedule a follow-up"

    if risk_level == "LOW" and is_overdue:
        return "Review the close date"

    return "Continue monitoring"