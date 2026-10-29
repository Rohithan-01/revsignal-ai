import math
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engine.activity_engine import normalize_activity_timestamp


class DealResponse(BaseModel):
    id: int
    company: str
    deal_value: float
    stage: str
    probability: float
    risk_level: str
    overall_risk_level: str
    risk_reasons: list[str]
    is_overdue: bool
    activity_status: str
    days_since_last_activity: int | None
    recommendation: str
    expected_close_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DealCreate(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    deal_value: float = Field(ge=0, allow_inf_nan=False)
    stage: str = Field(min_length=1, max_length=100)
    probability: float = Field(ge=0, le=100)
    expected_close_date: date | None = None

    @field_validator("expected_close_date", mode="before")
    @classmethod
    def require_calendar_date(cls, value: object) -> object:
        if value is None or isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("must be an ISO calendar date (YYYY-MM-DD)") from exc
            if parsed_date.isoformat() != value:
                raise ValueError("must be an ISO calendar date (YYYY-MM-DD)")
            return parsed_date
        raise ValueError("must be an ISO calendar date (YYYY-MM-DD)")

    @field_validator("deal_value", mode="before")
    @classmethod
    def reject_non_finite_deal_value(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            return "NaN and infinity are not valid deal values"
        return value

    @field_validator("company", "stage")
    @classmethod
    def require_non_whitespace_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")
        return value


class ActivityCreate(BaseModel):
    deal_id: int
    activity_type: str = Field(min_length=1, max_length=50)
    activity_date: datetime
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("activity_date")
    @classmethod
    def normalize_activity_date(cls, value: datetime) -> datetime:
        return normalize_activity_timestamp(value)

    @field_validator("activity_type")
    @classmethod
    def require_non_whitespace_activity_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")
        return value


class ActivityResponse(BaseModel):
    id: int
    deal_id: int
    activity_type: str
    activity_date: datetime
    notes: str | None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("activity_date", mode="before")
    @classmethod
    def normalize_response_activity_date(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class DealDetailResponse(DealResponse):
    latest_activity_date: datetime | None
    activities: list[ActivityResponse]