"""Domain enumerations. Values are stored as text in the database."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    REQUESTER = "REQUESTER"
    TEAM_LEADER = "TEAM_LEADER"
    DIRECTOR = "DIRECTOR"
    ENGINEER = "ENGINEER"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


class RequestType(StrEnum):
    PROJECT = "PROJECT"
    PRESALES = "PRESALES"
    OTHER = "OTHER"


class Priority(StrEnum):
    NORMAL = "NORMAL"
    URGENT = "URGENT"


class UrgencyReason(StrEnum):
    SHORT_NOTICE = "SHORT_NOTICE"
    DECLARED = "DECLARED"


class RequestStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_TL_REVIEW = "PENDING_TL_REVIEW"
    PENDING_DIRECTOR_APPROVAL = "PENDING_DIRECTOR_APPROVAL"
    RETURNED = "RETURNED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class ApprovalStep(StrEnum):
    TL_REVIEW = "TL_REVIEW"
    DIRECTOR_APPROVAL = "DIRECTOR_APPROVAL"
    CHANGE_REVIEW = "CHANGE_REVIEW"
    """Team leader review of a change to an approved request."""


class ChangeStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    RETURNED = "RETURNED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"
    """Closed without a decision by this assignee (another approver acted, or the request was withdrawn)."""


class AllocationStatus(StrEnum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"


class Action(StrEnum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    RETURN = "RETURN"
    REJECT = "REJECT"
    WITHDRAW = "WITHDRAW"
    CANCEL = "CANCEL"
    CLOSE = "CLOSE"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


OPEN_STATUSES = frozenset(
    {RequestStatus.PENDING_TL_REVIEW, RequestStatus.PENDING_DIRECTOR_APPROVAL, RequestStatus.RETURNED}
)
