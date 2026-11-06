from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from erf.db.models import Holiday, SupportType, SystemSetting
from erf.db.models import Sequence as SequenceRow

# Workflow parameters an administrator can change without a deployment.
SETTING_DEFAULTS: dict[str, tuple[str, str]] = {
    "min_notice_working_days": ("5", "Requests with less notice than this are urgent."),
    "tl_due_working_days": ("2", "Working days a team leader has before a reminder is sent."),
    "director_due_working_days": ("2", "Working days the director has before a reminder is sent."),
    "urgent_due_hours": ("4", "Hours an approver has for an urgent request before a reminder is sent."),
    "reminder_interval_hours": ("24", "Minimum hours between two reminders for the same urgent task."),
    "escalate_after_reminders": (
        "2",
        "From this reminder of an urgent task onwards, the director is copied.",
    ),
    "email_link_valid_days": ("7", "Days an approve, return or reject link in an email stays valid."),
    "request_no_prefix": ("ERR", "Prefix of request numbers, for example ERR-2026-0001."),
}


class SettingsRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, key: str) -> str:
        row = self.s.get(SystemSetting, key)
        if row is not None:
            return row.value
        return SETTING_DEFAULTS[key][0]

    def get_int(self, key: str) -> int:
        return int(self.get(key))

    def all(self) -> dict[str, tuple[str, str]]:
        values = {k: v for k, v in SETTING_DEFAULTS.items()}
        for row in self.s.scalars(select(SystemSetting)):
            if row.key in values:
                values[row.key] = (row.value, values[row.key][1])
        return values

    def set(self, key: str, value: str) -> None:
        if key not in SETTING_DEFAULTS:
            raise KeyError(key)
        row = self.s.get(SystemSetting, key)
        if row is None:
            self.s.add(SystemSetting(key=key, value=value, description=SETTING_DEFAULTS[key][1]))
        else:
            row.value = value

    def next_sequence(self, name: str, year: int) -> int:
        row = self.s.get(SequenceRow, (name, year))
        if row is None:
            row = SequenceRow(name=name, year=year, next_value=1)
            self.s.add(row)
        value = row.next_value
        row.next_value = value + 1
        self.s.flush()
        return value


class HolidayRepository:
    def __init__(self, session: Session):
        self.s = session

    def all_dates(self) -> list[date]:
        return list(self.s.scalars(select(Holiday.holiday_date)))

    def list_year(self, year: int | None = None) -> Sequence[Holiday]:
        stmt = select(Holiday).order_by(Holiday.holiday_date)
        if year is not None:
            stmt = stmt.where(
                Holiday.holiday_date >= date(year, 1, 1), Holiday.holiday_date <= date(year, 12, 31)
            )
        return self.s.scalars(stmt).all()

    def by_dates(self, first: date, last: date) -> Sequence[Holiday]:
        return self.s.scalars(
            select(Holiday).where(Holiday.holiday_date >= first, Holiday.holiday_date <= last)
        ).all()


class SupportTypeRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, type_id: int) -> SupportType | None:
        return self.s.get(SupportType, type_id)

    def list_all(self, *, active_only: bool = False) -> Sequence[SupportType]:
        stmt = select(SupportType).order_by(SupportType.sort_order, SupportType.name)
        if active_only:
            stmt = stmt.where(SupportType.is_active.is_(True))
        return self.s.scalars(stmt).unique().all()
