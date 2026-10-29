from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.database import Base


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    deal_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    account_name = synonym("company")
    deal_value: Mapped[float] = mapped_column(Float, nullable=False)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    created_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    activity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meeting_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stakeholder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="LOW"
    )
    risk_reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    recommended_action: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id"),
        nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
