from datetime import date, datetime, time, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class LegacyDateTimeDate(TypeDecorator[date]):
    """Map date values to the existing PostgreSQL timestamp column."""

    impl = DateTime(timezone=False)
    cache_ok = True

    def process_bind_param(self, value: date | None, _dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            raise TypeError("expected_close_date must be a date, not a datetime")
        return datetime.combine(value, time.min)

    def process_result_value(self, value: datetime | None, _dialect) -> date | None:
        if value is None:
            return None
        return value.date()


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company: Mapped[str] = mapped_column(String(255))
    deal_value: Mapped[float] = mapped_column(Float)
    stage: Mapped[str] = mapped_column(String(100))
    probability: Mapped[float] = mapped_column(Float)
    expected_close_date: Mapped[date | None] = mapped_column(
        LegacyDateTimeDate(), nullable=True
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