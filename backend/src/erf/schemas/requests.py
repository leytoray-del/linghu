from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from erf.domain.enums import Action, Priority, RequestStatus, RequestType
from erf.schemas.common import Schema, UserRef


class RequestIn(Schema):
    """Fields a requester can edit while the request is a draft or has been returned."""

    request_type: RequestType | None = None
    priority_declared: Priority = Priority.NORMAL
    project_name: str | None = Field(default=None, max_length=200)
    wbs_code: str | None = Field(default=None, max_length=64)
    client_name: str | None = Field(default=None, max_length=200)
    support_type_id: int | None = None
    headcount: int | None = Field(default=None, ge=1, le=50)
    preferred_engineer_ids: list[int] = Field(default_factory=list, max_length=20)
    preferred_engineers_note: str | None = Field(default=None, max_length=500)
    man_days: float | None = Field(default=None, gt=0, le=100000)
    planned_start: date | None = None
    planned_end: date | None = None
    scope_description: str | None = Field(default=None, max_length=10000)
    task_schedule: str | None = Field(default=None, max_length=5000)
    urgent_justification: str | None = Field(default=None, max_length=5000)

    @field_validator(
        "project_name",
        "wbs_code",
        "client_name",
        "preferred_engineers_note",
        "scope_description",
        "task_schedule",
        "urgent_justification",
    )
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class RequestUpdateIn(RequestIn):
    version: int


class VersionIn(Schema):
    version: int


class CommentIn(Schema):
    version: int
    comment: str | None = Field(default=None, max_length=5000)


class AllocationIn(Schema):
    engineer_id: int
    allocation_pct: int = Field(default=100, ge=25, le=100)


class DecisionIn(Schema):
    action: Action
    version: int
    comment: str | None = Field(default=None, max_length=5000)
    engineer_ids: list[int] = Field(default_factory=list, max_length=50)
    """Engineers assigned full time. Use ``allocations`` to set a percentage per engineer."""
    allocations: list[AllocationIn] = Field(default_factory=list, max_length=50)


class ChangeIn(Schema):
    version: int
    new_start: date
    new_end: date
    new_headcount: int = Field(ge=1, le=50)
    reason: str = Field(max_length=5000)


class ChangeDecisionIn(Schema):
    action: Action
    comment: str | None = Field(default=None, max_length=5000)
    allocations: list[AllocationIn] = Field(default_factory=list, max_length=50)


class NoticePreviewIn(Schema):
    planned_start: date


class HolidayOut(Schema):
    holiday_date: date
    name: str


class NoticePreviewOut(Schema):
    submitted_on: date
    planned_start: date
    notice_working_days: int
    min_notice_working_days: int
    is_short_notice: bool
    holidays: list[HolidayOut]


class SupportTypeBrief(Schema):
    id: int
    code: str
    name: str
    team_id: int


class TeamRef(Schema):
    id: int
    code: str
    name: str


class AllocationOut(Schema):
    id: int
    engineer: UserRef
    start_date: date
    end_date: date
    allocation_pct: int
    status: str


class ChangeOut(Schema):
    id: int
    status: str
    summary: str
    reason: str
    old_start: date
    old_end: date
    old_headcount: int | None
    new_start: date
    new_end: date
    new_headcount: int | None
    requested_by: UserRef
    decided_by: UserRef | None
    decision_comment: str | None
    decided_at: datetime | None
    created_at: datetime


class TaskOut(Schema):
    id: int
    round: int
    step: str
    assignee: UserRef
    status: str
    decision_comment: str | None
    due_at: datetime | None
    acted_at: datetime | None
    created_at: datetime


class EventOut(Schema):
    id: int
    action: str
    actor: UserRef | None
    from_status: str | None
    to_status: str | None
    comment: str | None
    payload: dict[str, object] | None
    created_at: datetime


class RequestSummary(Schema):
    id: int
    request_no: str | None
    display_no: str
    status: RequestStatus
    request_type: RequestType | None
    is_urgent: bool
    notice_working_days: int | None
    project_name: str | None
    client_name: str | None
    support_type: SupportTypeBrief | None
    team: TeamRef | None
    headcount: int | None
    planned_start: date | None
    planned_end: date | None
    requester: UserRef
    current_handlers: list[UserRef]
    submitted_at: datetime | None
    updated_at: datetime
    version: int


class RequestDetail(RequestSummary):
    priority_declared: Priority
    urgency_reason: str | None
    wbs_code: str | None
    preferred_engineers: list[UserRef]
    preferred_engineers_note: str | None
    man_days: float | None
    scope_description: str | None
    task_schedule: str | None
    urgent_justification: str | None
    round: int
    first_submitted_at: datetime | None
    decided_at: datetime | None
    allocations: list[AllocationOut]
    tasks: list[TaskOut]
    events: list[EventOut]
    available_actions: list[Action]
    can_edit: bool
    can_delete: bool
    changes: list[ChangeOut]
    can_request_change: bool
    change_awaiting_me: int | None
    """Id of a pending change the current user can approve or reject."""


class CandidateAssignment(Schema):
    request_id: int
    display_no: str
    project_name: str | None
    start_date: date
    end_date: date
    allocation_pct: int
    status: str


class AllocationCandidate(Schema):
    engineer: UserRef
    skills: str | None
    is_preferred: bool
    overlapping: list[CandidateAssignment]
    peak_pct: int
    """Highest weekly booking from other requests within this request's period."""


class TaskInboxItem(Schema):
    task_id: int
    step: str
    due_at: datetime | None
    is_overdue: bool
    request: RequestSummary
    change_summary: str | None = None


class EmailActionOut(Schema):
    """What the confirmation page behind an email link needs."""

    step: str
    assignee: UserRef
    expires_at: datetime
    actions: list[Action]
    request: RequestDetail
    change: ChangeOut | None
    candidates: list[AllocationCandidate]
    preselected: list[AllocationIn]


class EmailActionIn(Schema):
    action: Action
    comment: str | None = Field(default=None, max_length=5000)
    allocations: list[AllocationIn] = Field(default_factory=list, max_length=50)


class EmailActionResult(Schema):
    message: str
    request_id: int
    display_no: str
    status: RequestStatus
