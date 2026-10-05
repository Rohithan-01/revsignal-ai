from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company: Mapped[str] = mapped_column(String(255))
    deal_value: Mapped[float] = mapped_column(Float)
    stage: Mapped[str] = mapped_column(String(100))
    probability: Mapped[float] = mapped_column(Float)
    expected_close_date: Mapped[datetime | None] = mapped_column(
       DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id"),
        nullable=False
    )

    activity_type: Mapped[str] = mapped_column(String(50))

    activity_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )