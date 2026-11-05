"""Map ORM objects to response schemas. Kept in one place so every endpoint presents data consistently."""

from __future__ import annotations

import json

from erf.db.models import ResourceRequest, User
from erf.domain.enums import RequestStatus, TaskStatus
from erf.schemas.common import UserRef
from erf.schemas.requests import (
    AllocationOut,
    ChangeOut,
    EventOut,
    RequestDetail,
    RequestSummary,
    SupportTypeBrief,
    TaskOut,
    TeamRef,
)
from erf.services.workflow_service import WorkflowService


def user_ref(u: User) -> UserRef:
    return UserRef(id=u.id, display_name=u.display_name, email=u.email, job_title=u.job_title)


def current_handlers(r: ResourceRequest) -> list[UserRef]:
    status = r.status_enum
    if status in (RequestStatus.DRAFT, RequestStatus.RETURNED):
        return [user_ref(r.requester)]
    if status in (RequestStatus.PENDING_TL_REVIEW, RequestStatus.PENDING_DIRECTOR_APPROVAL):
        return [user_ref(t.assignee) for t in r.tasks if t.status == TaskStatus.PENDING.value]
    return []


def summary(r: ResourceRequest) -> RequestSummary:
    return RequestSummary(
        id=r.id,
        request_no=r.request_no,
        display_no=r.display_no,
        status=r.status_enum,
        request_type=r.request_type,
        is_urgent=r.is_urgent,
        notice_working_days=r.notice_working_days,
        project_name=r.project_name,
        client_name=r.client_name,
        support_type=SupportTypeBrief.model_validate(r.support_type) if r.support_type else None,
        team=TeamRef.model_validate(r.team) if r.team else None,
        headcount=r.headcount,
        planned_start=r.planned_start,
        planned_end=r.planned_end,
        requester=user_ref(r.requester),
        current_handlers=current_handlers(r),
        submitted_at=r.submitted_at,
        updated_at=r.updated_at,
        version=r.version,
    )


def detail(
    r: ResourceRequest,
    *,
    preferred: list[User],
    available_actions: list[str],
    can_edit: bool,
    can_delete: bool,
    can_request_change: bool = False,
    change_awaiting_me: int | None = None,
) -> RequestDetail:
    base = summary(r).model_dump()
    return RequestDetail(
        **base,
        priority_declared=r.priority_declared,
        urgency_reason=r.urgency_reason,
        wbs_code=r.wbs_code,
        preferred_engineers=[user_ref(u) for u in preferred],
        preferred_engineers_note=r.preferred_engineers_note,
        man_days=r.man_days,
        scope_description=r.scope_description,
        task_schedule=r.task_schedule,
        urgent_justification=r.urgent_justification,
        round=r.round,
        first_submitted_at=r.first_submitted_at,
        decided_at=r.decided_at,
        allocations=[
            AllocationOut(
                id=a.id,
                engineer=user_ref(a.engineer),
                start_date=a.start_date,
                end_date=a.end_date,
                allocation_pct=a.allocation_pct,
                status=a.status,
            )
            for a in r.allocations
            if a.status != "RELEASED"
        ],
        tasks=[
            TaskOut(
                id=t.id,
                round=t.round,
                step=t.step,
                assignee=user_ref(t.assignee),
                status=t.status,
                decision_comment=t.decision_comment,
                due_at=t.due_at,
                acted_at=t.acted_at,
                created_at=t.created_at,
            )
            for t in r.tasks
        ],
        events=[
            EventOut(
                id=e.id,
                action=e.action,
                actor=user_ref(e.actor) if e.actor else None,
                from_status=e.from_status,
                to_status=e.to_status,
                comment=e.comment,
                payload=json.loads(e.payload) if e.payload else None,
                created_at=e.created_at,
            )
            for e in r.events
        ],
        available_actions=available_actions,
        can_edit=can_edit,
        can_delete=can_delete,
        changes=[
            ChangeOut(
                id=c.id,
                status=c.status,
                summary=WorkflowService.describe_change(c),
                reason=c.reason,
                old_start=c.old_start,
                old_end=c.old_end,
                old_headcount=c.old_headcount,
                new_start=c.new_start,
                new_end=c.new_end,
                new_headcount=c.new_headcount,
                requested_by=user_ref(c.requested_by),
                decided_by=user_ref(c.decided_by) if c.decided_by else None,
                decision_comment=c.decision_comment,
                decided_at=c.decided_at,
                created_at=c.created_at,
            )
            for c in r.changes
        ],
        can_request_change=can_request_change,
        change_awaiting_me=change_awaiting_me,
    )
