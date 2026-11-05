from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from erf.api.deps import Ctx, CurrentUser
from erf.domain.enums import Action, RequestStatus
from erf.schemas.common import Page
from erf.schemas.requests import (
    AllocationCandidate,
    ChangeDecisionIn,
    ChangeIn,
    CommentIn,
    DecisionIn,
    NoticePreviewIn,
    NoticePreviewOut,
    RequestDetail,
    RequestIn,
    RequestSummary,
    RequestUpdateIn,
    TaskInboxItem,
    VersionIn,
)
from erf.services.access import ListScope
from erf.services.report_service import ReportService
from erf.services.request_service import RequestService
from erf.services.resource_service import ResourceService
from erf.services.workflow_service import WorkflowService

router = APIRouter(prefix="/requests", tags=["requests"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])

StatusFilter = Annotated[list[RequestStatus] | None, Query(alias="status")]


@router.get("", response_model=Page[RequestSummary])
def list_requests(
    user: CurrentUser,
    ctx: Ctx,
    scope: ListScope = ListScope.MINE,
    statuses: StatusFilter = None,
    urgent: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[RequestSummary]:
    return RequestService(ctx).search(
        user, scope, statuses=statuses or [], urgent_only=urgent, query=q, page=page, page_size=page_size
    )


@router.get("/export.xlsx", response_class=Response)
def export_requests(
    user: CurrentUser, ctx: Ctx, scope: ListScope = ListScope.MINE, statuses: StatusFilter = None
) -> Response:
    content = ReportService(ctx).export_xlsx(user, scope, statuses or [])
    filename = f"resource-requests-{ctx.clock.today().isoformat()}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/notice-preview", response_model=NoticePreviewOut)
def notice_preview(body: NoticePreviewIn, user: CurrentUser, ctx: Ctx) -> NoticePreviewOut:
    return RequestService(ctx).notice_preview(body.planned_start)


@router.post("", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def create_request(body: RequestIn, user: CurrentUser, ctx: Ctx, submit: bool = False) -> RequestDetail:
    service = RequestService(ctx)
    request = service.create_and_submit(user, body) if submit else service.create_draft(user, body)
    ctx.session.flush()
    return service.to_detail(user, request)


@router.get("/{request_id}", response_model=RequestDetail)
def get_request(request_id: int, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    return service.to_detail(user, service.load_visible(user, request_id))


@router.put("/{request_id}", response_model=RequestDetail)
def update_request(request_id: int, body: RequestUpdateIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = service.update(user, request_id, body, body.version)
    return service.to_detail(user, request)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(request_id: int, user: CurrentUser, ctx: Ctx) -> Response:
    RequestService(ctx).delete_draft(user, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{request_id}/submit", response_model=RequestDetail)
def submit_request(request_id: int, body: VersionIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = WorkflowService(ctx).submit(user, service.load_visible(user, request_id), body.version)
    return service.to_detail(user, request)


@router.post("/{request_id}/decision", response_model=RequestDetail)
def decide(request_id: int, body: DecisionIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = WorkflowService(ctx).decide(
        user,
        service.load_visible(user, request_id),
        body.action,
        comment=body.comment,
        version=body.version,
        engineer_ids=body.engineer_ids,
        allocations=[(a.engineer_id, a.allocation_pct) for a in body.allocations],
    )
    return service.to_detail(user, request)


@router.post("/{request_id}/withdraw", response_model=RequestDetail)
def withdraw(request_id: int, body: CommentIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = WorkflowService(ctx).withdraw(
        user, service.load_visible(user, request_id), comment=body.comment, version=body.version
    )
    return service.to_detail(user, request)


@router.post("/{request_id}/cancel", response_model=RequestDetail)
def cancel(request_id: int, body: CommentIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = WorkflowService(ctx).cancel(
        user, service.load_visible(user, request_id), comment=body.comment, version=body.version
    )
    return service.to_detail(user, request)


@router.post("/{request_id}/close", response_model=RequestDetail)
def close(request_id: int, body: VersionIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = WorkflowService(ctx).close(user, service.load_visible(user, request_id), version=body.version)
    return service.to_detail(user, request)


@router.post("/{request_id}/changes", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def request_change(request_id: int, body: ChangeIn, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = service.load_visible(user, request_id)
    WorkflowService(ctx).request_change(
        user,
        request,
        new_start=body.new_start,
        new_end=body.new_end,
        new_headcount=body.new_headcount,
        reason=body.reason,
        version=body.version,
    )
    return service.to_detail(user, request)


@router.post("/{request_id}/changes/{change_id}/decision", response_model=RequestDetail)
def decide_change(
    request_id: int, change_id: int, body: ChangeDecisionIn, user: CurrentUser, ctx: Ctx
) -> RequestDetail:
    service = RequestService(ctx)
    request = service.load_visible(user, request_id)
    WorkflowService(ctx).decide_change(
        user,
        request,
        change_id,
        body.action,
        comment=body.comment,
        allocations=[(a.engineer_id, a.allocation_pct) for a in body.allocations],
    )
    return service.to_detail(user, request)


@router.post("/{request_id}/changes/{change_id}/withdraw", response_model=RequestDetail)
def withdraw_change(request_id: int, change_id: int, user: CurrentUser, ctx: Ctx) -> RequestDetail:
    service = RequestService(ctx)
    request = service.load_visible(user, request_id)
    WorkflowService(ctx).withdraw_change(user, request, change_id)
    return service.to_detail(user, request)


@router.get("/{request_id}/candidates", response_model=list[AllocationCandidate])
def allocation_candidates(
    request_id: int, user: CurrentUser, ctx: Ctx, start: date | None = None, end: date | None = None
) -> list[AllocationCandidate]:
    return ResourceService(ctx).candidates(user, request_id, start, end)


@tasks_router.get("/mine", response_model=list[TaskInboxItem])
def my_tasks(user: CurrentUser, ctx: Ctx) -> list[TaskInboxItem]:
    return RequestService(ctx).inbox(user)


__all__ = ["Action", "router", "tasks_router"]
