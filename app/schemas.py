from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DealResponse(BaseModel):
    id: int
    company: str
    deal_value: float
    stage: str
    probability: float
    expected_close_date: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DealCreate(BaseModel):
    company: str
    deal_value: float
    stage: str
    probability: float
    expected_close_date: datetime | None = None