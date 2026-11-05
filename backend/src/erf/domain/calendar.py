"""Working-day arithmetic that excludes weekends and public holidays."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


class WorkingCalendar:
    def __init__(self, holidays: Iterable[date] = ()):
        self._holidays = frozenset(holidays)

    def is_working_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self._holidays

    def notice_working_days(self, submitted_on: date, start_on: date) -> int:
        """Working days strictly after the submission date and strictly before the start date.

        A request submitted on Thursday for a start on the following Thursday, with no holidays,
        has a notice period of four working days (Fri, Mon, Tue, Wed).
        """
        if start_on <= submitted_on:
            return 0
        count = 0
        day = submitted_on + timedelta(days=1)
        while day < start_on:
            if self.is_working_day(day):
                count += 1
            day += timedelta(days=1)
        return count

    def add_working_days(self, start: date, days: int) -> date:
        """The date that is ``days`` working days after ``start``."""
        day = start
        remaining = days
        while remaining > 0:
            day += timedelta(days=1)
            if self.is_working_day(day):
                remaining -= 1
        return day

    def holidays_between(self, first: date, last: date) -> list[date]:
        return sorted(h for h in self._holidays if first <= h <= last)
