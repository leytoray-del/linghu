"""Scheduled summary emails: a daily approvals digest for each approver and a weekly summary for directors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from erf.db.models import ApprovalTask, NotificationOutbox, ResourceRequest, User
from erf.domain.enums import ChangeStatus, OutboxStatus, RequestStatus, Role, TaskStatus
from erf.repositories.users import UserRepository
from erf.services.action_links import review_url
from erf.services.context import ServiceContext
from erf.services.notifications import NotificationService
from erf.services.workflow_service import WorkflowService

STEP_LABEL = {
    "TL_REVIEW": "Team leader review",
    "DIRECTOR_APPROVAL": "Director approval",
    "CHANGE_REVIEW": "Change review",
}
OPEN = (RequestStatus.PENDING_TL_REVIEW.value, RequestStatus.PENDING_DIRECTOR_APPROVAL.value)


@dataclass(frozen=True, slots=True)
class DigestRow:
    no: str
    project: str
    client: str
    requester: str
    step: str
    start: date | None
    waiting_days: int
    due: str
    overdue: bool
    urgent: bool
    note: str | None
    link: str


class DigestService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.env = NotificationService._env

    # ------------------------------------------------------------------ helpers

    def _link(self, request_id: int | None = None, path: str | None = None) -> str:
        base = self.ctx.settings.base_url.rstrip("/")
        return f"{base}/requests/{request_id}" if request_id else f"{base}{path or '/'}"

    def _local_midnight_utc(self, day: date) -> datetime:
        local = datetime.combine(day, time(0, 0), tzinfo=self.ctx.clock.tz)
        return local.astimezone(UTC).replace(tzinfo=None)

    def _already_sent(self, event: str, address: str, since: datetime) -> bool:
        rows = self.s.scalars(
            select(NotificationOutbox.to_addresses).where(
                NotificationOutbox.event_type == event, NotificationOutbox.created_at >= since
            )
        )
        return any(address in json.loads(r) for r in rows)

    def _enqueue(
        self, event: str, user: User, subject: str, template: str, context: dict[str, object]
    ) -> None:
        context = {"app_name": self.ctx.settings.app_name, **context}
        self.s.add(
            NotificationOutbox(
                event_type=event,
                request_id=None,
                to_addresses=json.dumps([user.email]),
                cc_addresses="[]",
                subject=subject[:255],
                body_html=self.env.get_template(f"{template}.html").render(**context),
                body_text=self.env.get_template(f"{template}.txt").render(**context),
                status=OutboxStatus.PENDING.value,
                created_at=self.ctx.clock.now(),
                next_attempt_at=self.ctx.clock.now(),
            )
        )

    def _waiting_days(self, since: datetime) -> int:
        return max(0, (self.ctx.clock.today() - self.ctx.clock.to_local(since).date()).days)

    # ------------------------------------------------------------------ daily digest

    def daily(self) -> int:
        """One email per approver who has pending tasks. Skipped on weekends and public holidays."""
        today = self.ctx.clock.today()
        if not self.ctx.calendar.is_working_day(today):
            return 0
        now = self.ctx.clock.now()
        tasks = self.s.scalars(
            select(ApprovalTask).where(ApprovalTask.status == TaskStatus.PENDING.value)
        ).all()
        by_user: dict[int, list[ApprovalTask]] = {}
        for t in tasks:
            by_user.setdefault(t.assignee_id, []).append(t)
        since = self._local_midnight_utc(today)
        sent = 0
        for user_id, user_tasks in by_user.items():
            user = UserRepository(self.s).get(user_id)
            if user is None or not user.is_active or self._already_sent("DAILY_DIGEST", user.email, since):
                continue
            rows = [self._row(t, now) for t in user_tasks]
            rows.sort(key=lambda r: (not r.overdue, not r.urgent, r.start or date.max))
            overdue = sum(1 for r in rows if r.overdue)
            subject = f"Approvals waiting for you: {len(rows)}" + (f" ({overdue} overdue)" if overdue else "")
            self._enqueue(
                "DAILY_DIGEST",
                user,
                subject,
                "digest",
                {"user": user, "rows": rows, "overdue": overdue, "inbox": self._link(path="/approvals")},
            )
            sent += 1
        return sent

    def _row(self, task: ApprovalTask, now: datetime) -> DigestRow:
        r: ResourceRequest = task.request
        note = None
        if task.change_id:
            change = next((c for c in r.changes if c.id == task.change_id), None)
            note = f"Change: {WorkflowService.describe_change(change)}" if change else None
        return DigestRow(
            no=r.display_no,
            project=r.project_name or "",
            client=r.client_name or "",
            requester=r.requester.display_name,
            step=STEP_LABEL.get(task.step, task.step),
            start=r.planned_start,
            waiting_days=self._waiting_days(task.created_at),
            due=self.ctx.clock.to_local(task.due_at).strftime("%d %b %H:%M") if task.due_at else "-",
            overdue=bool(task.due_at and task.due_at < now),
            urgent=r.is_urgent,
            note=note,
            link=review_url(self.ctx, task),
        )

    # ------------------------------------------------------------------ weekly summary

    def weekly(self) -> int:
        """A management summary for directors: last week's activity, open approvals and upcoming starts."""
        today = self.ctx.clock.today()
        now = self.ctx.clock.now()
        week_ago = now - timedelta(days=7)
        horizon = today + timedelta(days=14)
        requests = self.s.scalars(
            select(ResourceRequest).where(ResourceRequest.status != RequestStatus.DRAFT.value)
        ).all()

        submitted = [r for r in requests if r.first_submitted_at and r.first_submitted_at >= week_ago]
        approved = [
            r
            for r in requests
            if r.decided_at and r.decided_at >= week_ago and r.status in ("APPROVED", "CLOSED")
        ]
        # Rejections this week: sent back for revision (RETURN) and permanent (REJECT).
        rejected = [
            e
            for r in requests
            for e in r.events
            if e.action in ("RETURN", "REJECT") and e.created_at >= week_ago
        ]
        changes = [
            c
            for r in requests
            for c in r.changes
            if c.status == ChangeStatus.APPROVED.value and c.decided_at and c.decided_at >= week_ago
        ]
        waiting = sorted(
            (r for r in requests if r.status in OPEN),
            key=lambda r: r.submitted_at or now,
        )
        waiting_rows = [
            {
                "r": r,
                "days": self._waiting_days(r.submitted_at or now),
                "with": ", ".join(
                    t.assignee.display_name
                    for t in r.tasks
                    if t.status == TaskStatus.PENDING.value and not t.change_id
                ),
                "overdue": any(
                    t.status == TaskStatus.PENDING.value and t.due_at and t.due_at < now for t in r.tasks
                ),
                "link": self._link(r.id),
            }
            for r in waiting
        ]
        starting = [
            r
            for r in requests
            if r.planned_start
            and today <= r.planned_start <= horizon
            and r.status in ("APPROVED", *OPEN, RequestStatus.RETURNED.value)
        ]
        starting.sort(key=lambda r: r.planned_start or today)
        short_notice = [r for r in submitted if r.urgency_reason == "SHORT_NOTICE"]

        context = {
            "week_start": (today - timedelta(days=7)).strftime("%d %b"),
            "week_end": (today - timedelta(days=1)).strftime("%d %b %Y"),
            "submitted": len(submitted),
            "urgent": sum(1 for r in submitted if r.is_urgent),
            "approved": len(approved),
            "rejected": len(rejected),
            "changes": len(changes),
            "waiting": waiting_rows,
            "starting": [
                {"r": r, "confirmed": r.status == "APPROVED", "link": self._link(r.id)} for r in starting
            ],
            "short_notice": short_notice,
            "dashboard": self._link(path="/reports"),
        }
        sent = 0
        since = now - timedelta(days=6)
        for director in UserRepository(self.s).with_role(Role.DIRECTOR):
            if self._already_sent("WEEKLY_SUMMARY", director.email, since):
                continue
            self._enqueue(
                "WEEKLY_SUMMARY",
                director,
                f"Weekly resource summary, week ending {context['week_end']}",
                "weekly",
                {"user": director, **context},
            )
            sent += 1
        return sent
