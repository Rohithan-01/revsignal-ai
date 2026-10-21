from __future__ import annotations

from datetime import datetime


def generate_recommendation(
    risk_level: str,
    days_since_activity: int | None,
    expected_close_date: datetime | None,
    stakeholder_count: int | None,
    stage: str,
    reason_count: int,
) -> str:
    if expected_close_date is not None and expected_close_date < datetime.now():
        return "Review the close date, confirm customer commitment, and escalate the account if the renewal decision is still pending."

    if days_since_activity is not None and days_since_activity > 30:
        return "Schedule a customer follow-up within 48 hours and confirm the buying timeline, next milestones, and open questions."

    if stakeholder_count is not None and stakeholder_count < 2:
        return "Identify missing decision-makers and validate the buying committee before the next customer conversation."

    if stage.lower() in {"proposal", "negotiation"} and reason_count >= 3:
        return "Reassess the opportunity plan, address the blockers, and clarify the expected decision path with the customer."

    if risk_level == "HIGH":
        return "Run a focused deal review with the account team and document the immediate actions needed to reduce risk."

    if risk_level == "MEDIUM":
        return "Stay engaged with the customer, confirm the next milestone, and monitor the deal closely over the next two weeks."

    return "Maintain the current outreach cadence and validate the next customer milestone to keep momentum."
