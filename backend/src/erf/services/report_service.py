"""Dashboard counters, yearly statistics and Excel export."""

from __future__ import annotations

import io
from collections import Counter
from datetime import datetime
from statistics import median

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from erf.core.errors import Forbidden
from erf.db.models import ResourceRequest, User
from erf.domain.enums import AllocationStatus, ApprovalStep, RequestStatus, Role
from erf.repositories.requests import RequestFilter, RequestRepository, TaskRepository
from erf.schemas.reports import DashboardOut, MonthCount, NamedCount, ReportSummary
from erf.services.access import AccessPolicy, ListScope
from erf.services.context import ServiceContext
from erf.services.request_service import RequestService

STATUS_LABEL = {
    RequestStatus.DRAFT: "Draft",
    RequestStatus.PENDING_TL_REVIEW: "Pending team leader review",
    RequestStatus.PENDING_DIRECTOR_APPROVAL: "Pending director approval",
    RequestStatus.RETURNED: "Rejected, can resubmit",
    RequestStatus.APPROVED: "Approved",
    RequestStatus.REJECTED: "Rejected permanently",
    RequestStatus.WITHDRAWN: "Withdrawn",
    RequestStatus.CANCELLED: "Cancelled",
    RequestStatus.CLOSED: "Closed",
}
TYPE_LABEL = {"PROJECT": "Project", "PRESALES": "Pre-sales", "OTHER": "Other"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class ReportService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.repo = RequestRepository(ctx.session)
        self.access = AccessPolicy(ctx.session)

    def dashboard(self, user: User) -> DashboardOut:
        mine = self.repo.all_matching(RequestFilter(requester_id=user.id))
        counts = Counter(r.status for r in mine)
        tasks = TaskRepository(self.s).pending_for_user(user.id)
        now = self.ctx.clock.now()
        led = self.access.led_team_ids(user)
        team_open = 0
        if led:
            team_open = len(
                self.repo.all_matching(
                    RequestFilter(
                        team_ids=led,
                        statuses=[RequestStatus.PENDING_TL_REVIEW, RequestStatus.PENDING_DIRECTOR_APPROVAL],
                    )
                )
            )
        assigned = 0
        if user.has_role(Role.ENGINEER):
            assigned = len(
                self.repo.all_matching(RequestFilter(engineer_id=user.id, statuses=[RequestStatus.APPROVED]))
            )
        return DashboardOut(
            my_open=counts[RequestStatus.PENDING_TL_REVIEW] + counts[RequestStatus.PENDING_DIRECTOR_APPROVAL],
            my_returned=counts[RequestStatus.RETURNED],
            my_approved=counts[RequestStatus.APPROVED],
            my_drafts=counts[RequestStatus.DRAFT],
            my_total=len(mine) - counts[RequestStatus.DRAFT],
            pending_tasks=len(tasks),
            pending_urgent=sum(1 for t in tasks if t.request.is_urgent),
            overdue_tasks=sum(1 for t in tasks if t.due_at and t.due_at < now),
            team_requests_open=team_open,
            assigned_active=assigned,
        )

    def _report_filter(self, user: User) -> RequestFilter:
        if user.has_role(Role.DIRECTOR, Role.ADMIN, Role.VIEWER):
            return RequestFilter(exclude_drafts=True)
        led = self.access.led_team_ids(user)
        if not led:
            raise Forbidden("Reports are available to team leaders, directors and administrators.")
        return RequestFilter(team_ids=led, exclude_drafts=True)

    def summary(self, user: User, year: int) -> ReportSummary:
        f = self._report_filter(user)
        f.year = year
        rows = self.repo.all_matching(f)
        by_month = {m: [0, 0] for m in range(1, 13)}
        for r in rows:
            assert r.first_submitted_at is not None
            month = self.ctx.clock.to_local(r.first_submitted_at).month
            by_month[month][1 if r.is_urgent else 0] += 1
        approved = [r for r in rows if r.status in (RequestStatus.APPROVED.value, RequestStatus.CLOSED.value)]
        request_ids = {r.id for r in rows}
        tl_hours: list[float] = []
        dir_hours: list[float] = []
        for t in TaskRepository(self.s).decided(datetime(year, 1, 1)):
            if t.request_id not in request_ids or t.acted_at is None:
                continue
            hours = (t.acted_at - t.created_at).total_seconds() / 3600
            (tl_hours if t.step == ApprovalStep.TL_REVIEW.value else dir_hours).append(hours)
        urgent = sum(1 for r in rows if r.is_urgent)
        return ReportSummary(
            year=year,
            total=len(rows),
            urgent=urgent,
            urgent_share=round(urgent / len(rows), 3) if rows else 0.0,
            approved=len(approved),
            approved_man_days=sum(r.man_days or 0 for r in approved),
            median_tl_hours=round(median(tl_hours), 1) if tl_hours else None,
            median_director_hours=round(median(dir_hours), 1) if dir_hours else None,
            by_month=[MonthCount(month=MONTHS[m - 1], normal=v[0], urgent=v[1]) for m, v in by_month.items()],
            by_status=_counts(STATUS_LABEL[RequestStatus(r.status)] for r in rows),
            by_support_type=_counts(r.support_type.name for r in rows if r.support_type),
            by_team=_counts(r.team.name for r in rows if r.team),
        )

    def export_xlsx(self, user: User, scope: ListScope, statuses: list[RequestStatus]) -> bytes:
        f = RequestService(self.ctx).filter_for(user, scope)
        f.statuses = statuses
        rows = self.repo.all_matching(f)
        wb = Workbook()
        ws = wb.active
        ws.title = "Requests"
        headers = [
            "Request no.", "Status", "Request type", "Priority", "Notice (working days)", "Project / opportunity",
            "WBS code", "Client", "Type of support", "Team", "Engineers required", "Man-days", "Planned start",
            "Planned end", "Requester", "Allocated engineers", "Submitted", "Decided", "Scope description",
            "Task schedule", "Urgent justification",
        ]  # fmt: skip
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2254C5")
        for r in rows:
            ws.append(_row(r, self.ctx))
        for i, width in enumerate(
            [16, 26, 12, 10, 10, 34, 14, 20, 20, 20, 10, 10, 13, 13, 20, 30, 18, 18, 60, 40, 40], 1
        ):
            ws.column_dimensions[get_column_letter(i)].width = width
        ws.freeze_panes = "A2"
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


def _counts(values: object) -> list[NamedCount]:
    c = Counter(values)  # type: ignore[call-overload]
    return [NamedCount(name=k, count=v) for k, v in c.most_common()]


def _row(r: ResourceRequest, ctx: ServiceContext) -> list[object]:
    def local(dt: datetime | None) -> str:
        return ctx.clock.to_local(dt).strftime("%Y-%m-%d %H:%M") if dt else ""

    engineers = ", ".join(
        a.engineer.display_name for a in r.allocations if a.status != AllocationStatus.RELEASED.value
    )
    return [
        r.display_no,
        STATUS_LABEL[RequestStatus(r.status)],
        TYPE_LABEL.get(r.request_type or "", ""),
        "Urgent" if r.is_urgent else "Normal",
        r.notice_working_days,
        r.project_name,
        r.wbs_code,
        r.client_name,
        r.support_type.name if r.support_type else "",
        r.team.name if r.team else "",
        r.headcount,
        r.man_days,
        r.planned_start,
        r.planned_end,
        r.requester.display_name,
        engineers,
        local(r.first_submitted_at),
        local(r.decided_at),
        r.scope_description,
        r.task_schedule,
        r.urgent_justification,
    ]
