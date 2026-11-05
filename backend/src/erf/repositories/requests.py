from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from erf.db.models import (
    ApprovalTask,
    NotificationOutbox,
    ResourceAllocation,
    ResourceRequest,
    User,
)
from erf.domain.enums import AllocationStatus, OutboxStatus, RequestStatus, TaskStatus


@dataclass(slots=True)
class RequestFilter:
    requester_id: int | None = None
    team_ids: list[int] | None = None
    engineer_id: int | None = None
    statuses: list[RequestStatus] = field(default_factory=list)
    exclude_drafts: bool = False
    urgent_only: bool = False
    query: str | None = None
    year: int | None = None


class RequestRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, request_id: int) -> ResourceRequest | None:
        return self.s.get(ResourceRequest, request_id)

    def add(self, request: ResourceRequest) -> ResourceRequest:
        self.s.add(request)
        self.s.flush()
        return request

    def delete(self, request: ResourceRequest) -> None:
        self.s.delete(request)

    def _filtered(self, f: RequestFilter) -> Select[ResourceRequest]:
        stmt = select(ResourceRequest)
        if f.requester_id is not None:
            stmt = stmt.where(ResourceRequest.requester_id == f.requester_id)
        if f.team_ids is not None:
            stmt = stmt.where(ResourceRequest.team_id.in_(f.team_ids))
        if f.engineer_id is not None:
            stmt = stmt.where(
                ResourceRequest.id.in_(
                    select(ResourceAllocation.request_id).where(
                        ResourceAllocation.engineer_id == f.engineer_id,
                        ResourceAllocation.status != AllocationStatus.RELEASED.value,
                    )
                )
            )
        if f.statuses:
            stmt = stmt.where(ResourceRequest.status.in_([s.value for s in f.statuses]))
        if f.exclude_drafts:
            stmt = stmt.where(ResourceRequest.status != RequestStatus.DRAFT.value)
        if f.urgent_only:
            stmt = stmt.where(ResourceRequest.is_urgent.is_(True))
        if f.year is not None:
            stmt = stmt.where(
                ResourceRequest.first_submitted_at >= datetime(f.year, 1, 1),
                ResourceRequest.first_submitted_at < datetime(f.year + 1, 1, 1),
            )
        if f.query:
            like = f"%{f.query.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(ResourceRequest.project_name).like(like),
                    func.lower(ResourceRequest.client_name).like(like),
                    func.lower(ResourceRequest.request_no).like(like),
                    func.lower(ResourceRequest.wbs_code).like(like),
                )
            )
        return stmt

    def search(
        self, f: RequestFilter, *, offset: int = 0, limit: int = 50
    ) -> tuple[Sequence[ResourceRequest], int]:
        base = self._filtered(f)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = (
            self.s.scalars(
                base.order_by(ResourceRequest.updated_at.desc(), ResourceRequest.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .unique()
            .all()
        )
        return rows, total

    def all_matching(self, f: RequestFilter) -> Sequence[ResourceRequest]:
        return self.s.scalars(self._filtered(f).order_by(ResourceRequest.id)).unique().all()

    def due_for_close(self, today: date) -> Sequence[ResourceRequest]:
        return (
            self.s.scalars(
                select(ResourceRequest).where(
                    ResourceRequest.status == RequestStatus.APPROVED.value,
                    ResourceRequest.planned_end < today,
                )
            )
            .unique()
            .all()
        )


class TaskRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, task: ApprovalTask) -> None:
        self.s.add(task)

    def pending_for_user(self, user_id: int) -> Sequence[ApprovalTask]:
        return (
            self.s.scalars(
                select(ApprovalTask)
                .where(ApprovalTask.assignee_id == user_id, ApprovalTask.status == TaskStatus.PENDING.value)
                .order_by(ApprovalTask.created_at)
            )
            .unique()
            .all()
        )

    def overdue(self, now: datetime) -> Sequence[ApprovalTask]:
        return (
            self.s.scalars(
                select(ApprovalTask).where(
                    ApprovalTask.status == TaskStatus.PENDING.value, ApprovalTask.due_at < now
                )
            )
            .unique()
            .all()
        )

    def decided(self, since: datetime) -> Sequence[ApprovalTask]:
        return self.s.scalars(
            select(ApprovalTask).where(
                ApprovalTask.acted_at.is_not(None),
                ApprovalTask.acted_at >= since,
                ApprovalTask.status.in_(
                    [TaskStatus.APPROVED.value, TaskStatus.RETURNED.value, TaskStatus.REJECTED.value]
                ),
            )
        ).all()


class AllocationRepository:
    def __init__(self, session: Session):
        self.s = session

    def active_in_period(
        self, engineer_ids: list[int], first: date, last: date, *, exclude_request_id: int | None = None
    ) -> Sequence[ResourceAllocation]:
        if not engineer_ids:
            return []
        stmt = select(ResourceAllocation).where(
            ResourceAllocation.engineer_id.in_(engineer_ids),
            ResourceAllocation.status != AllocationStatus.RELEASED.value,
            ResourceAllocation.start_date <= last,
            ResourceAllocation.end_date >= first,
        )
        if exclude_request_id is not None:
            stmt = stmt.where(ResourceAllocation.request_id != exclude_request_id)
        return self.s.scalars(stmt.order_by(ResourceAllocation.start_date)).unique().all()


class OutboxRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: NotificationOutbox) -> None:
        self.s.add(row)

    def due(self, now: datetime, limit: int = 20) -> Sequence[NotificationOutbox]:
        return self.s.scalars(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status == OutboxStatus.PENDING.value,
                NotificationOutbox.next_attempt_at <= now,
            )
            .order_by(NotificationOutbox.id)
            .limit(limit)
        ).all()

    def recent(self, limit: int = 100, status: OutboxStatus | None = None) -> Sequence[NotificationOutbox]:
        stmt = select(NotificationOutbox).order_by(NotificationOutbox.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(NotificationOutbox.status == status.value)
        return self.s.scalars(stmt).all()

    def get(self, row_id: int) -> NotificationOutbox | None:
        return self.s.get(NotificationOutbox, row_id)

    def counts(self) -> dict[str, int]:
        rows = self.s.execute(
            select(NotificationOutbox.status, func.count()).group_by(NotificationOutbox.status)
        ).all()
        return {status: int(n) for status, n in rows}


def user_names(session: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(session.execute(select(User.id, User.display_name).where(User.id.in_(ids))).tuples().all())
