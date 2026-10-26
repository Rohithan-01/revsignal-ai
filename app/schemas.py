from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    expected_close_date: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DealCreate(BaseModel):
    company: str
    deal_value: float
    stage: str
    probability: float = Field(ge=0, le=100)
    expected_close_date: datetime | None = None

class ActivityCreate(BaseModel):
    deal_id: int
    activity_type: str
    activity_date: datetime
    notes: str | None = None


class ActivityResponse(BaseModel):
    id: int
    deal_id: int
    activity_type: str
    activity_date: datetime
    notes: str | None

    model_config = ConfigDict(from_attributes=True)


class DealDetailResponse(DealResponse):
    latest_activity_date: datetime | None
    activities: list[ActivityResponse]