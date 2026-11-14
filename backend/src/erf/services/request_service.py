"""Use cases around a single request: drafting, editing, viewing, listing and notice preview."""

from __future__ import annotations

from datetime import date

from erf.core.errors import Forbidden, NotFound, ValidationFailed
from erf.db.models import RequestEvent, RequestPreferredEngineer, ResourceRequest, User
from erf.domain.enums import RequestStatus, TaskStatus
from erf.domain.permissions import Permission
from erf.domain.workflow import available_actions
from erf.repositories.requests import RequestFilter, RequestRepository, TaskRepository
from erf.repositories.settings import HolidayRepository, SupportTypeRepository
from erf.repositories.users import UserRepository
from erf.schemas.common import Page
from erf.schemas.requests import (
    HolidayOut,
    NoticePreviewOut,
    RequestDetail,
    RequestIn,
    RequestSummary,
    TaskInboxItem,
)
from erf.services import presenters
from erf.services.access import AccessPolicy, ListScope
from erf.services.context import ServiceContext
from erf.services.permission_service import can
from erf.services.workflow_service import WorkflowService

EDITABLE_STATUSES = (RequestStatus.DRAFT, RequestStatus.RETURNED)


class RequestService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.repo = RequestRepository(ctx.session)
        self.access = AccessPolicy(ctx.session)
        self.workflow = WorkflowService(ctx)

    # ------------------------------------------------------------------ loading

    def load(self, request_id: int) -> ResourceRequest:
        request = self.repo.get(request_id)
        if request is None:
            raise NotFound("This request does not exist.")
        return request

    def load_visible(self, user: User, request_id: int) -> ResourceRequest:
        request = self.load(request_id)
        self.access.require_view(user, request)
        return request

    def to_detail(self, user: User, request: ResourceRequest) -> RequestDetail:
        caps = self.access.capacities(user, request)
        is_owner = request.requester_id == user.id
        preferred = list(UserRepository(self.s).get_many(request.preferred_engineer_ids))
        pending = self.workflow.pending_change(request)
        awaiting = None
        if pending and any(
            t.change_id == pending.id and t.assignee_id == user.id and t.status == TaskStatus.PENDING.value
            for t in request.tasks
        ):
            awaiting = pending.id
        return presenters.detail(
            request,
            preferred=preferred,
            available_actions=[a.value for a in available_actions(request.status_enum, caps)],
            can_edit=is_owner and request.status_enum in EDITABLE_STATUSES,
            can_delete=is_owner and request.status_enum == RequestStatus.DRAFT,
            can_request_change=is_owner and request.status_enum == RequestStatus.APPROVED and pending is None,
            change_awaiting_me=awaiting,
        )

    # ------------------------------------------------------------------ drafting

    def _apply_fields(self, request: ResourceRequest, data: RequestIn) -> None:
        if data.support_type_id is not None:
            support_type = SupportTypeRepository(self.s).get(data.support_type_id)
            if support_type is None:
                raise ValidationFailed(
                    "Choose a valid type of support.",
                    details={"fields": {"support_type_id": "Choose a type of support from the list."}},
                )
            request.team_id = support_type.team_id
        if data.preferred_engineer_ids:
            engineers = UserRepository(self.s).get_many(data.preferred_engineer_ids)
            if len(engineers) != len(set(data.preferred_engineer_ids)) or any(
                not can(self.s, u, Permission.RESOURCES_ASSIGNABLE) for u in engineers
            ):
                raise ValidationFailed(
                    "Preferred engineers must be chosen from the engineer list.",
                    details={"fields": {"preferred_engineer_ids": "Choose engineers from the list."}},
                )
        for name in (
            "request_type",
            "priority_declared",
            "project_name",
            "wbs_code",
            "client_name",
            "support_type_id",
            "headcount",
            "preferred_engineers_note",
            "man_days",
            "planned_start",
            "planned_end",
            "scope_description",
            "task_schedule",
            "urgent_justification",
        ):
            value = getattr(data, name)
            setattr(request, name, value.value if hasattr(value, "value") else value)
        request.preferred_rows = [
            RequestPreferredEngineer(user_id=i) for i in dict.fromkeys(data.preferred_engineer_ids)
        ]

    def create_draft(self, user: User, data: RequestIn) -> ResourceRequest:
        request = ResourceRequest(
            requester_id=user.id, requester=user, status=RequestStatus.DRAFT.value, round=0
        )
        self._apply_fields(request, data)
        self.repo.add(request)
        request.events.append(
            RequestEvent(
                actor_id=user.id, action="CREATE", to_status=request.status, created_at=self.ctx.clock.now()
            )
        )
        self.s.flush()
        return request

    def update(self, user: User, request_id: int, data: RequestIn, version: int) -> ResourceRequest:
        request = self.load_visible(user, request_id)
        if request.requester_id != user.id:
            raise Forbidden("Only the requester can edit this request.")
        if request.status_enum not in EDITABLE_STATUSES:
            raise Forbidden("This request can no longer be edited.")
        self.workflow.check_version(request, version)
        self._apply_fields(request, data)
        self.s.flush()
        return request

    def delete_draft(self, user: User, request_id: int) -> None:
        request = self.load_visible(user, request_id)
        if request.requester_id != user.id or request.status_enum != RequestStatus.DRAFT:
            raise Forbidden("Only your own drafts can be deleted.")
        self.repo.delete(request)

    def create_and_submit(self, user: User, data: RequestIn) -> ResourceRequest:
        request = self.create_draft(user, data)
        return self.workflow.submit(user, request, request.version)

    # ------------------------------------------------------------------ queries

    def search(
        self,
        user: User,
        scope: ListScope,
        *,
        statuses: list[RequestStatus],
        urgent_only: bool = False,
        query: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Page[RequestSummary]:
        f = self.filter_for(user, scope)
        f.statuses = statuses
        f.urgent_only = urgent_only
        f.query = query
        rows, total = self.repo.search(f, offset=(page - 1) * page_size, limit=page_size)
        return Page[RequestSummary](
            items=[presenters.summary(r) for r in rows], total=total, page=page, page_size=page_size
        )

    def filter_for(self, user: User, scope: ListScope) -> RequestFilter:
        self.access.require_scope(user, scope)
        if scope == ListScope.MINE:
            return RequestFilter(requester_id=user.id)
        if scope == ListScope.TEAM:
            return RequestFilter(team_ids=self.access.led_team_ids(user), exclude_drafts=True)
        if scope == ListScope.ASSIGNED:
            return RequestFilter(engineer_id=user.id, exclude_drafts=True)
        return RequestFilter(exclude_drafts=True)

    def inbox(self, user: User) -> list[TaskInboxItem]:
        now = self.ctx.clock.now()
        items = []
        for task in TaskRepository(self.s).pending_for_user(user.id):
            r = task.request
            change = next((c for c in r.changes if c.id == task.change_id), None) if task.change_id else None
            items.append(
                TaskInboxItem(
                    task_id=task.id,
                    step=task.step,
                    due_at=task.due_at,
                    is_overdue=bool(task.due_at and task.due_at < now),
                    request=presenters.summary(r),
                    change_summary=self.workflow.describe_change(change) if change else None,
                )
            )
        items.sort(key=lambda i: (not i.request.is_urgent, i.request.planned_start or date.max))
        return items

    def pending_task_count(self, user: User) -> int:
        return len(TaskRepository(self.s).pending_for_user(user.id))

    def notice_preview(self, planned_start: date) -> NoticePreviewOut:
        today = self.ctx.clock.today()
        notice = self.ctx.calendar.notice_working_days(today, planned_start)
        minimum = self.ctx.config.get_int("min_notice_working_days")
        holidays = HolidayRepository(self.s).by_dates(today, planned_start) if planned_start > today else []
        return NoticePreviewOut(
            submitted_on=today,
            planned_start=planned_start,
            notice_working_days=notice,
            min_notice_working_days=minimum,
            is_short_notice=notice < minimum,
            holidays=[HolidayOut(holiday_date=h.holiday_date, name=h.name) for h in holidays],
        )
