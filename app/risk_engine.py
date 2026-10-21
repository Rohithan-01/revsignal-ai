from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.recommendation_engine import generate_recommendation


def _coerce_date(value: Any) -> datetime | None:
    if value in (None, "", "nan", "NaN"):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(cleaned, fmt)
                except ValueError:
                    continue
    return None


def _normalize_status(value: Any) -> str:
    text = str(value or "open").strip().lower().replace(" ", "_")
    if text in {"open", "active", "pipeline", "in_progress", "in-progress", "qualified", "proposal", "negotiation", "discovery"}:
        return "open"
    if text in {"won", "closed_won", "close_won"}:
        return "won"
    if text in {"lost", "closed_lost", "close_lost"}:
        return "lost"
    return text or "open"


def analyze_deal(record: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stage = str(record.get("stage") or "Unknown").strip() or "Unknown"
    status = _normalize_status(record.get("status"))
    deal_value = float(record.get("deal_value") or 0)
    created_date = _coerce_date(record.get("created_date"))
    expected_close_date = _coerce_date(record.get("expected_close_date"))
    last_activity_date = _coerce_date(record.get("last_activity_date"))
    activity_count = record.get("activity_count")
    meeting_count = record.get("meeting_count")
    email_count = record.get("email_count")
    stakeholder_count = record.get("stakeholder_count")

    reasons: list[str] = []
    score = 0

    if last_activity_date is None:
        score += 20
        reasons.append("No recent customer activity was provided, so engagement is uncertain.")
    else:
        if last_activity_date.tzinfo is None:
            last_activity_date = last_activity_date.replace(tzinfo=timezone.utc)
        days_since_activity = (now - last_activity_date).days
        if days_since_activity > 45:
            score += 35
            reasons.append(f"The last customer activity was {days_since_activity} days ago.")
        elif days_since_activity > 21:
            score += 18
            reasons.append(f"Customer activity has slowed; it has been {days_since_activity} days since the last touchpoint.")

    if expected_close_date is not None:
        close_dt = expected_close_date
        if close_dt.tzinfo is None:
            close_dt = close_dt.replace(tzinfo=timezone.utc)
        days_to_close = (close_dt - now).days
        if days_to_close < 0:
            score += 25
            reasons.append("The expected close date is overdue.")
        elif days_to_close <= 14:
            score += 12
            reasons.append("The expected close date is approaching within two weeks.")

    if created_date is not None:
        if created_date.tzinfo is None:
            created_date = created_date.replace(tzinfo=timezone.utc)
        days_in_stage = (now - created_date).days
        if stage.lower() in {"proposal", "negotiation", "qualified", "discovery"} and days_in_stage > 60:
            score += 15
            reasons.append(f"This opportunity has been in the {stage} stage for more than 60 days.")
        elif stage.lower() in {"proposal", "negotiation"} and days_in_stage > 30:
            score += 10
            reasons.append(f"This deal has been in the {stage} stage for more than 30 days.")

    if activity_count is not None:
        if activity_count <= 1:
            score += 12
            reasons.append("The opportunity has very limited recent activity and a low engagement signal.")
        elif activity_count <= 3:
            score += 6
            reasons.append("Activity volume is low relative to the expected customer engagement pattern.")

    if meeting_count is not None and meeting_count == 0:
        score += 10
        reasons.append("No meetings have been recorded for this opportunity.")

    if email_count is not None and email_count == 0:
        score += 8
        reasons.append("Email engagement is currently flat or missing.")

    if stakeholder_count is not None and stakeholder_count < 2:
        score += 12
        reasons.append("Stakeholder coverage appears limited, which can reduce buying committee alignment.")

    if stage.lower() == "discovery" and status == "open":
        score += 5
        reasons.append("This deal is still in discovery, which may require additional qualification and executive alignment.")

    if deal_value < 25000 and status == "open":
        score += 5
        reasons.append("The deal value is relatively small, which can increase the need for tighter pipeline prioritization.")

    score = max(0, min(100, score))

    if score < 35:
        risk_level = "LOW"
    elif score < 70:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    recommended_action = generate_recommendation(
        risk_level=risk_level,
        days_since_activity=(None if last_activity_date is None else (now - last_activity_date).days),
        expected_close_date=expected_close_date,
        stakeholder_count=stakeholder_count,
        stage=stage,
        reason_count=len(reasons),
    )

    return {
        "deal_id": str(record.get("deal_id") or "UNKNOWN"),
        "account_name": str(record.get("account_name") or "Unknown account"),
        "deal_value": float(deal_value),
        "stage": stage,
        "status": status,
        "created_date": created_date,
        "expected_close_date": expected_close_date,
        "last_activity_date": last_activity_date,
        "activity_count": int(activity_count) if activity_count is not None else None,
        "meeting_count": int(meeting_count) if meeting_count is not None else None,
        "email_count": int(email_count) if email_count is not None else None,
        "stakeholder_count": int(stakeholder_count) if stakeholder_count is not None else None,
        "risk_score": score,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "recommended_action": recommended_action,
    }
