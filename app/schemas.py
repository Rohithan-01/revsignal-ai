from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DealResponse(BaseModel):
    id: int
    company: str
    deal_value: float
    stage: str
    probability: float
    risk_level: str
    is_overdue: bool
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