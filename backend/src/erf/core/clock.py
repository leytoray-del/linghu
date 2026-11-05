"""Injectable clock so that date-dependent rules (notice period, reminders) are testable."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class Clock:
    def __init__(self, tz_name: str):
        self.tz = ZoneInfo(tz_name)

    def now(self) -> datetime:
        """Current time as a naive UTC datetime (the storage convention)."""
        return datetime.now(UTC).replace(tzinfo=None)

    def today(self) -> date:
        """Current business date in the configured time zone."""
        return self.to_local(self.now()).date()

    def to_local(self, utc_naive: datetime) -> datetime:
        return utc_naive.replace(tzinfo=UTC).astimezone(self.tz)


class FixedClock(Clock):
    """A clock that returns a set moment. Used by tests and the demo seeder."""

    def __init__(self, tz_name: str, at: datetime):
        super().__init__(tz_name)
        self._at = at

    def set(self, at: datetime) -> None:
        self._at = at

    def advance(self, **kwargs: float) -> None:
        self._at = self._at + timedelta(**kwargs)

    def now(self) -> datetime:
        return self._at
