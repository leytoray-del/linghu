"""Per-unit-of-work dependencies shared by all services."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from erf.core.clock import Clock
from erf.core.config import Settings
from erf.domain.calendar import WorkingCalendar
from erf.repositories.settings import HolidayRepository, SettingsRepository


@dataclass
class ServiceContext:
    session: Session
    clock: Clock
    settings: Settings
    _calendar: WorkingCalendar | None = field(default=None, init=False, repr=False)

    @property
    def calendar(self) -> WorkingCalendar:
        if self._calendar is None:
            self._calendar = WorkingCalendar(HolidayRepository(self.session).all_dates())
        return self._calendar

    @property
    def config(self) -> SettingsRepository:
        return SettingsRepository(self.session)
