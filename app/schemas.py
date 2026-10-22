from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DealRead(BaseModel):
    id: Optional[int] = None
    deal_id: str
    account_name: str
    deal_value: float
    stage: str
    status: str
    created_date: Optional[datetime] = None
    expected_close_date: Optional[datetime] = None
    last_activity_date: Optional[datetime] = None
    activity_count: Optional[int] = None
    meeting_count: Optional[int] = None
    email_count: Optional[int] = None
    stakeholder_count: Optional[int] = None
    risk_score: int = 0
    risk_level: str = "LOW"
    risk_reasons: list[str] = Field(default_factory=list)
    recommended_action: str = ""


class UploadResponse(BaseModel):
    success: bool
    message: str
    records_imported: int


class MetricsResponse(BaseModel):
    total_open_pipeline_value: float
    revenue_high_risk: float
    high_risk_deals: int
    deals_needing_attention: int
    deal_distribution_by_risk: dict[str, int]
    pipeline_value_by_stage: dict[str, float]
    top_deals: list[dict]
