from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    deal_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    deal_value: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(100), default="Unknown")
    status: Mapped[str] = mapped_column(String(50), default="open")
    created_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meeting_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stakeholder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW")
    risk_reasons: Mapped[str] = mapped_column(Text, default="[]")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
