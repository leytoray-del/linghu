"""Background jobs. Each job runs in its own unit of work and is safe to run again after a failure."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from erf.core.clock import Clock
from erf.core.config import Settings
from erf.db.session import session_scope
from erf.domain.enums import ApprovalStep, OutboxStatus, TaskStatus
from erf.infrastructure.mail.senders import MailSender, OutgoingMail
from erf.repositories.requests import OutboxRepository, RequestRepository, TaskRepository
from erf.repositories.users import SessionRepository
from erf.services.context import ServiceContext
from erf.services.notifications import Event, NotificationService
from erf.services.workflow_service import WorkflowService

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 8


def dispatch_outbox(factory: sessionmaker[Session], clock: Clock, sender: MailSender, batch: int = 20) -> int:
    """Send due emails. Failures are retried with exponential back-off, up to ``MAX_ATTEMPTS``."""
    sent = 0
    with session_scope(factory) as session:
        for row in OutboxRepository(session).due(clock.now(), batch):
            mail = OutgoingMail(
                to=json.loads(row.to_addresses),
                cc=json.loads(row.cc_addresses),
                subject=row.subject,
                html=row.body_html,
                text=row.body_text,
            )
            row.attempts += 1
            try:
                sender.send(mail)
            except Exception as exc:
                row.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = OutboxStatus.FAILED.value
                    log.error("Email %s failed permanently: %s", row.id, row.last_error)
                else:
                    row.next_attempt_at = clock.now() + timedelta(minutes=min(2**row.attempts, 240))
                    log.warning("Email %s failed (attempt %s): %s", row.id, row.attempts, row.last_error)
            else:
                row.status = OutboxStatus.SENT.value
                row.sent_at = clock.now()
                row.last_error = None
                sent += 1
            session.flush()
    return sent


def send_reminders(factory: sessionmaker[Session], clock: Clock, settings: Settings) -> int:
    """Remind approvers about overdue tasks. From the configured reminder onwards, copy the director."""
    count = 0
    with session_scope(factory) as session:
        ctx = ServiceContext(session, clock, settings)
        interval = timedelta(hours=ctx.config.get_int("reminder_interval_hours"))
        escalate_after = ctx.config.get_int("escalate_after_reminders")
        notifications = NotificationService(ctx)
        workflow = WorkflowService(ctx)
        now = clock.now()
        for task in TaskRepository(session).overdue(now):
            if task.status != TaskStatus.PENDING.value:
                continue
            if task.last_reminded_at and now - task.last_reminded_at < interval:
                continue
            if task.assignee_id is None or not ctx.calendar.is_working_day(clock.today()):
                continue
            task.reminded_count += 1
            task.last_reminded_at = now
            cc = []
            if task.reminded_count >= escalate_after and task.step == ApprovalStep.TL_REVIEW.value:
                cc = workflow.directors()
            waiting = clock.to_local(task.created_at).strftime("%d %b %Y %H:%M")
            notifications.notify(
                Event.TASK_REMINDER, task.request, to=[task.assignee], cc=cc, extra={"waiting_since": waiting}
            )
            count += 1
    return count


def auto_close(factory: sessionmaker[Session], clock: Clock, settings: Settings) -> int:
    """Close approved requests whose planned end date has passed."""
    with session_scope(factory) as session:
        ctx = ServiceContext(session, clock, settings)
        workflow = WorkflowService(ctx)
        due = RequestRepository(session).due_for_close(clock.today())
        for request in due:
            workflow.close(None, request)
        return len(due)


def purge_sessions(factory: sessionmaker[Session], clock: Clock) -> int:
    with session_scope(factory) as session:
        return SessionRepository(session).purge_expired(clock.now())
