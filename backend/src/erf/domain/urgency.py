"""Urgency classification rule from the resource request policy."""

from __future__ import annotations

from dataclasses import dataclass

from erf.domain.enums import Priority, UrgencyReason


@dataclass(frozen=True, slots=True)
class UrgencyResult:
    is_urgent: bool
    reason: UrgencyReason | None
    notice_working_days: int
    is_short_notice: bool


def evaluate_urgency(declared: Priority, notice_working_days: int, min_notice: int) -> UrgencyResult:
    """A request with less than ``min_notice`` working days of notice is urgent regardless of what the
    requester chose. A requester may also declare a request urgent with enough notice."""
    short = notice_working_days < min_notice
    if short:
        return UrgencyResult(True, UrgencyReason.SHORT_NOTICE, notice_working_days, True)
    if declared == Priority.URGENT:
        return UrgencyResult(True, UrgencyReason.DECLARED, notice_working_days, False)
    return UrgencyResult(False, None, notice_working_days, False)
