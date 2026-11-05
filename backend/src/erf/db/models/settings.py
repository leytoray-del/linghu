from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from erf.db.base import Base, TimestampMixin


class Holiday(TimestampMixin, Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    holiday_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class Sequence(Base):
    """Per-year counters for human-readable request numbers."""

    __tablename__ = "sequences"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
