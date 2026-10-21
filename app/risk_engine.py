from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DealRead(BaseModel):
    id: int
    deal_id: str
    account_name: str
    deal_value: float
    stage: str
    status: str
    created_date: datetime | None = None
    expected_close_date: datetime | None = None
    last_activity_date: datetime | None = None
    activity_count: int | None = None
    meeting_count: int | None = None
    email_count: int | None = None
    stakeholder_count: int | None = None
    risk_score: int = 0
    risk_level: str = "LOW"
    risk_reasons: list[str] = Field(default_factory=list)
    recommended_action: str = ""


class DealMetrics(BaseModel):
    total_open_pipeline_value: float
    revenue_high_risk: float
    high_risk_deals: int
    deals_needing_attention: int
    deal_distribution_by_risk: dict[str, int]
    pipeline_value_by_stage: dict[str, float]
    top_deals: list[DealRead]


class UploadResponse(BaseModel):
    success: bool
    message: str
    records_imported: int
