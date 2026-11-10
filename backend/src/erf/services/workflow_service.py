"""Applies state-machine transitions: tasks, allocations, audit events and notifications.

Every method runs inside the caller's unit of work, so a transition and everything it causes
(including queued emails) is committed together or not at all.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from email.utils import parseaddr
from typing import Any

from sqlalchemy import select

from erf.core.errors import Conflict, Forbidden, ValidationFailed
from erf.db.models import (
    ApprovalTask,
    RequestChange,
    RequestEvent,
    ResourceAllocation,
    ResourceRequest,
    User,
)
from erf.domain.enums import (
    Action,
    AllocationStatus,
    ApprovalStep,
    ChangeStatus,
    Priority,
    RequestStatus,
    RequestType,
    Role,
    TaskStatus,
)
from erf.domain.urgency import evaluate_urgency
from erf.domain.validation import SubmissionFields, validate_submission
from erf.domain.workflow import STEP_FOR_STATUS, Actor, Transition, find_transition
from erf.infrastructure.calendar_ics import assignment_invite
from erf.infrastructure.mail.senders import Attachment, is_placeholder
from erf.repositories.settings import SupportTypeRepository
from erf.repositories.users import TeamRepository, UserRepository
from erf.services.access import AccessPolicy
from erf.services.action_links import links_for
from erf.services.context import ServiceContext
from erf.services.notifications import Event, NotificationService

AllocationSpec = tuple[int, int]
"""(engineer id, allocation percentage)."""

ALLOWED_PCTS = frozenset({25, 50, 75, 100})

TASK_RESULT = {
    Action.APPROVE: TaskStatus.APPROVED,
    Action.RETURN: TaskStatus.RETURNED,
    Action.REJECT: TaskStatus.REJECTED,
}


class WorkflowService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.access = AccessPolicy(ctx.session)
        self.users = UserRepository(ctx.session)
        self.notifications = NotificationService(ctx)

    # ------------------------------------------------------------------ helpers

    def check_version(self, request: ResourceRequest, version: int | None) -> None:
        if version is not None and version != request.version:
            raise Conflict(
                "Someone else changed this request after you opened it. Refresh the page and try again.",
                details={"current_version": request.version},
            )

    def _authorise(self, user: User | None, request: ResourceRequest, transition: Transition) -> Actor:
        if user is None:
            if Actor.SYSTEM in transition.actors:
                return Actor.SYSTEM
            raise Forbidden("Sign in to do this.")
        caps = self.access.capacities(user, request) & transition.actors
        if not caps:
            if Actor.STEP_ASSIGNEE in transition.actors:
                raise Forbidden("This request is not waiting for your decision.")
            raise Forbidden("Only the requester or an administrator can do this.")
        for preferred in (Actor.STEP_ASSIGNEE, Actor.REQUESTER, Actor.ADMIN):
            if preferred in caps:
                return preferred
        return next(iter(caps))

    def _event(
        self,
        request: ResourceRequest,
        actor: User | None,
        action: str,
        from_status: str | None,
        comment: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        request.events.append(
            RequestEvent(
                actor_id=actor.id if actor else None,
                action=action,
                from_status=from_status,
                to_status=request.status,
                comment=comment or None,
                payload=json.dumps(payload, default=str) if payload else None,
                created_at=self.ctx.clock.now(),
            )
        )
        self.s.flush()

    def _pending_tasks(self, request: ResourceRequest) -> list[ApprovalTask]:
        return [t for t in request.tasks if t.status == TaskStatus.PENDING.value]

    def _close_pending_tasks(self, request: ResourceRequest, except_task: ApprovalTask | None = None) -> None:
        now = self.ctx.clock.now()
        for task in self._pending_tasks(request):
            if task is not except_task:
                task.status = TaskStatus.CLOSED.value
                task.acted_at = now

    def _active_allocations(self, request: ResourceRequest) -> list[ResourceAllocation]:
        return [a for a in request.allocations if a.status != AllocationStatus.RELEASED.value]

    def _release_allocations(self, request: ResourceRequest) -> list[User]:
        released = []
        for a in self._active_allocations(request):
            a.status = AllocationStatus.RELEASED.value
            released.append(a.engineer)
        return released

    def _team_approvers(self, request: ResourceRequest) -> list[User]:
        if request.team_id is None:
            return []
        team = TeamRepository(self.s).get(request.team_id)
        if team is None:
            return []
        return [u for u in self.users.get_many(team.approver_ids) if u.is_active]

    def directors(self) -> list[User]:
        return list(self.users.with_role(Role.DIRECTOR))

    def _due_at(self, request: ResourceRequest, step: ApprovalStep) -> Any:
        cfg = self.ctx.config
        now = self.ctx.clock.now()
        if request.is_urgent:
            return now + timedelta(hours=cfg.get_int("urgent_due_hours"))
        key = "tl_due_working_days" if step == ApprovalStep.TL_REVIEW else "director_due_working_days"
        today = self.ctx.clock.today()
        due_day = self.ctx.calendar.add_working_days(today, cfg.get_int(key))
        return now + timedelta(days=(due_day - today).days)

    def _create_tasks(
        self, request: ResourceRequest, step: ApprovalStep, assignees: Sequence[User]
    ) -> list[ApprovalTask]:
        due = self._due_at(request, step)
        created = []
        for user in assignees:
            task = ApprovalTask(
                round=request.round,
                step=step.value,
                assignee_id=user.id,
                assignee=user,
                status=TaskStatus.PENDING.value,
                due_at=due,
            )
            request.tasks.append(task)
            created.append(task)
        self.s.flush()
        return created

    def notify_tasks(
        self,
        event: Event,
        request: ResourceRequest,
        tasks: Sequence[ApprovalTask],
        *,
        actor: User | None,
        cc: Sequence[User] = (),
        comment: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> None:
        """One email per approver with their own approve, return and reject links, plus one information
        copy (without links) for ``cc``."""
        self.s.flush()
        for task in tasks:
            self.notifications.notify(
                event,
                request,
                to=[task.assignee],
                actor=actor,
                comment=comment,
                extra=extra,
                actions=links_for(self.ctx, task),
            )
        assignees = [t.assignee for t in tasks]
        copies = [u for u in cc if u not in assignees]
        if copies:
            self.notifications.notify(
                event, request, to=copies, actor=actor, comment=comment, extra=extra, copy_of=assignees
            )

    def _assign_request_no(self, request: ResourceRequest) -> None:
        if request.request_no:
            return
        cfg = self.ctx.config
        year = self.ctx.clock.today().year
        seq = cfg.next_sequence("request", year)
        request.request_no = f"{cfg.get('request_no_prefix')}-{year}-{seq:04d}"

    # ------------------------------------------------------------------ submit

    def submit(self, user: User, request: ResourceRequest, version: int | None) -> ResourceRequest:
        self.check_version(request, version)
        transition = find_transition(request.status_enum, Action.SUBMIT)
        self._authorise(user, request, transition)

        today = self.ctx.clock.today()
        support_type = (
            SupportTypeRepository(self.s).get(request.support_type_id) if request.support_type_id else None
        )
        cfg = self.ctx.config
        notice = (
            self.ctx.calendar.notice_working_days(today, request.planned_start)
            if request.planned_start
            else 0
        )
        urgency = evaluate_urgency(
            Priority(request.priority_declared), notice, cfg.get_int("min_notice_working_days")
        )
        errors = validate_submission(
            SubmissionFields(
                request_type=RequestType(request.request_type) if request.request_type else None,
                project_name=request.project_name,
                client_name=request.client_name,
                support_type_id=request.support_type_id,
                headcount=request.headcount,
                man_days=request.man_days,
                planned_start=request.planned_start,
                planned_end=request.planned_end,
                scope_description=request.scope_description,
                task_schedule=request.task_schedule,
                is_urgent=urgency.is_urgent,
                urgent_justification=request.urgent_justification,
            ),
            today,
        )
        if support_type is not None and not support_type.is_active:
            errors["support_type_id"] = "This type of support is no longer offered. Choose another one."
        if errors:
            raise ValidationFailed(
                "Some fields need attention before you can submit.", details={"fields": errors}
            )
        assert support_type is not None

        request.team_id = support_type.team_id
        request.team = support_type.team
        approvers = self._team_approvers(request)
        if not approvers:
            raise ValidationFailed(
                f"No team leader is set up for the {support_type.team.name}. Ask an administrator to assign one."
            )

        from_status = request.status
        resubmission = request.round > 0
        now = self.ctx.clock.now()
        self._assign_request_no(request)
        request.round += 1
        request.status = transition.target.value
        request.submitted_at = now
        request.first_submitted_at = request.first_submitted_at or now
        request.decided_at = None
        request.notice_working_days = urgency.notice_working_days
        request.is_urgent = urgency.is_urgent
        request.urgency_reason = urgency.reason.value if urgency.reason else None
        if urgency.is_short_notice:
            request.priority_declared = Priority.URGENT.value
        if (
            request.request_type != RequestType.PROJECT.value
            and request.man_days is not None
            and request.man_days <= 0
        ):
            request.man_days = None
        self._release_allocations(request)
        review_tasks = self._create_tasks(request, ApprovalStep.TL_REVIEW, approvers)
        self.s.flush()
        self._event(
            request,
            user,
            "RESUBMIT" if resubmission else "SUBMIT",
            from_status,
            payload={
                "round": request.round,
                "notice_working_days": urgency.notice_working_days,
                "is_urgent": urgency.is_urgent,
                "urgency_reason": request.urgency_reason,
            },
        )
        self.notify_tasks(Event.REQUEST_SUBMITTED, request, review_tasks, actor=user, cc=[user])
        return request

    # ------------------------------------------------------------------ decisions

    def decide(
        self,
        user: User,
        request: ResourceRequest,
        action: Action,
        *,
        comment: str | None,
        version: int | None,
        engineer_ids: list[int] | None = None,
        allocations: list[AllocationSpec] | None = None,
        via: str | None = None,
        client: dict[str, str] | None = None,
    ) -> ResourceRequest:
        if action not in TASK_RESULT:
            raise ValidationFailed("Choose approve or reject.")
        self.check_version(request, version)
        transition = find_transition(request.status_enum, action)
        self._authorise(user, request, transition)
        comment = (comment or "").strip() or None
        if transition.requires_comment and not comment:
            raise ValidationFailed(
                "Add a comment so the requester knows what to change or why the request was declined.",
                details={"fields": {"comment": "A comment is required."}},
            )

        step = STEP_FOR_STATUS[request.status_enum]
        task = next(
            t
            for t in self._pending_tasks(request)
            if t.assignee_id == user.id and t.step == step.value and t.round == request.round
        )

        allocation_names: list[str] = []
        if step == ApprovalStep.TL_REVIEW and action == Action.APPROVE:
            specs = self._specs(engineer_ids, allocations)
            self._check_allocation(request, specs, request.headcount, comment)
            assert request.planned_start and request.planned_end
            allocation_names = self._set_allocations(
                user, request, specs, AllocationStatus.PROPOSED, request.planned_start, request.planned_end
            )

        from_status = request.status
        now = self.ctx.clock.now()
        task.status = TASK_RESULT[action].value
        task.decision_comment = comment
        task.acted_at = now
        self._close_pending_tasks(request, except_task=task)
        request.status = transition.target.value

        payload: dict[str, Any] = {"step": step.value, "round": request.round}
        if via:
            payload["via"] = via
        if client:
            payload["client"] = client
        if allocation_names:
            payload["engineers"] = allocation_names

        if transition.target == RequestStatus.PENDING_DIRECTOR_APPROVAL:
            directors = self.directors()
            if not directors:
                raise ValidationFailed("No director is set up to give final approval. Ask an administrator.")
            director_tasks = self._create_tasks(request, ApprovalStep.DIRECTOR_APPROVAL, directors)
            self._event(request, user, "TL_APPROVE", from_status, comment, payload)
            self.notify_tasks(
                Event.TL_APPROVED,
                request,
                director_tasks,
                actor=user,
                cc=[request.requester],
                comment=comment,
            )
        elif transition.target == RequestStatus.APPROVED:
            for a in self._active_allocations(request):
                a.status = AllocationStatus.CONFIRMED.value
            request.decided_at = now
            self.s.flush()
            self._event(request, user, "DIRECTOR_APPROVE", from_status, comment, payload)
            no_invite = self._send_assignments(
                request,
                self._active_allocations(request),
                Event.ASSIGNMENT_INVITE,
                actor=user,
                sequence=self._calendar_sequence(request),
            )
            self.notifications.notify(
                Event.REQUEST_APPROVED,
                request,
                to=[request.requester, *no_invite],
                cc=self._team_approvers(request),
                actor=user,
                comment=comment,
            )
        elif transition.target == RequestStatus.RETURNED:
            self._release_allocations(request)
            self.s.flush()
            self._event(request, user, "RETURN", from_status, comment, payload)
            self.notifications.notify(
                Event.REQUEST_RETURNED,
                request,
                to=[request.requester],
                cc=[user],
                actor=user,
                comment=comment,
            )
        else:
            self._release_allocations(request)
            request.decided_at = now
            self.s.flush()
            self._event(request, user, "REJECT", from_status, comment, payload)
            self.notifications.notify(
                Event.REQUEST_REJECTED,
                request,
                to=[request.requester],
                cc=self._team_approvers(request),
                actor=user,
                comment=comment,
            )
        return request

    @staticmethod
    def _specs(
        engineer_ids: list[int] | None, allocations: list[AllocationSpec] | None
    ) -> list[AllocationSpec]:
        """Allocations as (engineer, percentage). A plain list of engineers means full-time assignment."""
        if allocations:
            return list({e: pct for e, pct in allocations}.items())
        return [(e, 100) for e in dict.fromkeys(engineer_ids or [])]

    def _check_allocation(
        self,
        request: ResourceRequest,
        specs: list[AllocationSpec],
        headcount: int | None,
        comment: str | None,
    ) -> None:
        if not specs:
            raise ValidationFailed(
                "Assign at least one engineer before approving.",
                details={"fields": {"engineer_ids": "Select at least one engineer."}},
            )
        if any(pct not in ALLOWED_PCTS for _, pct in specs):
            raise ValidationFailed("Choose an allocation of 25%, 50%, 75% or 100% for each engineer.")
        engineers = {u.id: u for u in self.users.get_many([e for e, _ in specs])}
        if any(
            e not in engineers
            or not engineers[e].is_active
            or not engineers[e].has_role(Role.ENGINEER)
            or engineers[e].team_id != request.team_id
            for e, _ in specs
        ):
            raise ValidationFailed(
                "Some selected people are not active engineers in this team.",
                details={
                    "fields": {"engineer_ids": "Choose engineers from the team that handles this request."}
                },
            )
        if headcount and len(specs) < headcount and not comment:
            raise ValidationFailed(
                f"You assigned {len(specs)} of {headcount} requested engineers. "
                "Add a comment that explains the shortfall.",
                details={"fields": {"comment": "Explain why fewer engineers are assigned."}},
            )

    def _set_allocations(
        self,
        user: User,
        request: ResourceRequest,
        specs: list[AllocationSpec],
        status: AllocationStatus,
        start: date,
        end: date,
    ) -> list[str]:
        """Make the active allocations match ``specs``: keep and update listed engineers, add new ones and
        release the rest. Returns "Name (pct%)" labels for the audit trail."""
        wanted = dict(specs)
        engineers = {u.id: u for u in self.users.get_many(list(wanted))}
        for a in self._active_allocations(request):
            if a.engineer_id in wanted:
                a.allocation_pct = wanted.pop(a.engineer_id)
                a.start_date, a.end_date, a.status = start, end, status.value
            else:
                a.status = AllocationStatus.RELEASED.value
        for engineer_id, pct in wanted.items():
            request.allocations.append(
                ResourceAllocation(
                    engineer_id=engineer_id,
                    engineer=engineers[engineer_id],
                    start_date=start,
                    end_date=end,
                    allocation_pct=pct,
                    status=status.value,
                    allocated_by_id=user.id,
                )
            )
        self.s.flush()
        return [f"{a.engineer.display_name} ({a.allocation_pct}%)" for a in self._active_allocations(request)]

    @staticmethod
    def _calendar_sequence(request: ResourceRequest) -> int:
        """Calendar updates must carry a higher SEQUENCE than earlier ones: one step per approved change."""
        return sum(1 for c in request.changes if c.status == ChangeStatus.APPROVED.value)

    def _send_assignments(
        self,
        request: ResourceRequest,
        allocations: Sequence[ResourceAllocation],
        event: Event,
        *,
        actor: User | None,
        sequence: int,
        comment: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> list[User]:
        """Send each engineer a personal calendar invitation (or cancellation for ASSIGNMENT_CANCELLED).
        Returns engineers with placeholder addresses (demo accounts), who cannot receive mail; callers
        include them in the ordinary email instead, so no invitations end up in the demo mailbox."""
        cancel = event == Event.ASSIGNMENT_CANCELLED
        method = "CANCEL" if cancel else "REQUEST"
        organizer_name, organizer_email = parseaddr(self.ctx.settings.mail_from)
        link = f"{self.ctx.settings.base_url.rstrip('/')}/requests/{request.id}"
        assert request.planned_start and request.planned_end
        period = f"{request.planned_start:%d %b %Y} to {request.planned_end:%d %b %Y}"
        skipped: list[User] = []
        for a in allocations:
            engineer = a.engineer
            if is_placeholder(engineer.email):
                skipped.append(engineer)
                continue
            invite = assignment_invite(
                request,
                engineer_name=engineer.display_name,
                engineer_email=engineer.email,
                allocation_pct=a.allocation_pct,
                method=method,
                organizer_name=organizer_name or self.ctx.settings.app_name,
                organizer_email=organizer_email or "no-reply@example.com",
                sequence=sequence,
                now_utc=self.ctx.clock.now(),
                link=link,
            )
            self.notifications.notify(
                event,
                request,
                to=[engineer],
                actor=actor,
                comment=comment,
                extra={**(extra or {}), "pct": str(a.allocation_pct), "period": period},
                attachments=[
                    Attachment(
                        filename="invite.ics",
                        content_type=f"text/calendar; method={method}; charset=UTF-8",
                        content=invite,
                        inline=True,
                    )
                ],
            )
        return skipped

    def _drop_pending_changes(self, request: ResourceRequest) -> None:
        """A cancelled or closed request cannot be changed any more."""
        now = self.ctx.clock.now()
        for change in request.changes:
            if change.status == ChangeStatus.PENDING.value:
                change.status = ChangeStatus.WITHDRAWN.value
                change.decided_at = now

    # ------------------------------------------------------------------ requester and system actions

    def withdraw(
        self, user: User, request: ResourceRequest, *, comment: str | None, version: int | None
    ) -> ResourceRequest:
        self.check_version(request, version)
        transition = find_transition(request.status_enum, Action.WITHDRAW)
        self._authorise(user, request, transition)
        pending_assignees = [t.assignee for t in self._pending_tasks(request)]
        from_status = request.status
        self._close_pending_tasks(request)
        released = self._release_allocations(request)
        request.status = transition.target.value
        request.decided_at = self.ctx.clock.now()
        self.s.flush()
        self._event(request, user, "WITHDRAW", from_status, comment)
        self.notifications.notify(
            Event.REQUEST_WITHDRAWN,
            request,
            to=[*pending_assignees, *released],
            cc=[request.requester],
            actor=user,
            comment=comment,
        )
        return request

    def cancel(
        self, user: User, request: ResourceRequest, *, comment: str | None, version: int | None
    ) -> ResourceRequest:
        self.check_version(request, version)
        transition = find_transition(request.status_enum, Action.CANCEL)
        self._authorise(user, request, transition)
        comment = (comment or "").strip() or None
        if not comment:
            raise ValidationFailed(
                "Explain why the approved request is being cancelled.",
                details={"fields": {"comment": "A comment is required."}},
            )
        from_status = request.status
        self._drop_pending_changes(request)
        self._close_pending_tasks(request)
        assigned = list(self._active_allocations(request))
        self._release_allocations(request)
        request.status = transition.target.value
        self.s.flush()
        self._event(request, user, "CANCEL", from_status, comment)
        no_invite = self._send_assignments(
            request,
            assigned,
            Event.ASSIGNMENT_CANCELLED,
            actor=user,
            sequence=self._calendar_sequence(request) + 1,
            comment=comment,
            extra={"reason": "the approved request was cancelled"},
        )
        self.notifications.notify(
            Event.REQUEST_CANCELLED,
            request,
            to=[*no_invite, *self._team_approvers(request)],
            cc=[request.requester],
            actor=user,
            comment=comment,
        )
        return request

    def close(
        self, user: User | None, request: ResourceRequest, *, version: int | None = None
    ) -> ResourceRequest:
        self.check_version(request, version)
        transition = find_transition(request.status_enum, Action.CLOSE)
        self._authorise(user, request, transition)
        from_status = request.status
        self._drop_pending_changes(request)
        self._close_pending_tasks(request)
        request.status = transition.target.value
        self.s.flush()
        self._event(
            request,
            user,
            "CLOSE",
            from_status,
            None if user else "Closed automatically after the planned end date.",
        )
        return request

    # ------------------------------------------------------------------ changes to approved requests

    def pending_change(self, request: ResourceRequest) -> RequestChange | None:
        return next((c for c in request.changes if c.status == ChangeStatus.PENDING.value), None)

    @staticmethod
    def describe_change(change: RequestChange) -> str:
        def period(a: date, b: date) -> str:
            return f"{a.strftime('%d %b %Y')} - {b.strftime('%d %b %Y')}"

        parts = []
        if (change.old_start, change.old_end) != (change.new_start, change.new_end):
            parts.append(
                f"period {period(change.old_start, change.old_end)} to {period(change.new_start, change.new_end)}"
            )
        if change.old_headcount != change.new_headcount:
            parts.append(f"engineers {change.old_headcount} to {change.new_headcount}")
        return "; ".join(parts) or "no change"

    def request_change(
        self,
        user: User,
        request: ResourceRequest,
        *,
        new_start: date,
        new_end: date,
        new_headcount: int,
        reason: str | None,
        version: int | None,
    ) -> RequestChange:
        """The requester asks to move the dates or change the headcount of an approved request."""
        self.check_version(request, version)
        if request.status_enum != RequestStatus.APPROVED:
            raise ValidationFailed("Only approved requests can be changed.")
        if request.requester_id != user.id:
            raise Forbidden("Only the requester can ask for a change.")
        if self.pending_change(request):
            raise Conflict("A change is already waiting for review. Withdraw it before asking for another.")
        reason = (reason or "").strip()
        today = self.ctx.clock.today()
        assert request.planned_start and request.planned_end
        errors: dict[str, str] = {}
        if not reason:
            errors["reason"] = "Explain why the change is needed."
        if new_end < new_start:
            errors["new_end"] = "The end date must be on or after the start date."
        if new_start != request.planned_start and new_start < today:
            errors["new_start"] = "A new start date cannot be in the past."
        if new_end < today:
            errors["new_end"] = "The end date cannot be in the past."
        if not 1 <= new_headcount <= 50:
            errors["new_headcount"] = "Enter between 1 and 50 engineers."
        if (new_start, new_end, new_headcount) == (
            request.planned_start,
            request.planned_end,
            request.headcount,
        ):
            errors["new_start"] = "Change the dates or the number of engineers."
        if errors:
            raise ValidationFailed("Some fields need attention.", details={"fields": errors})
        approvers = self._team_approvers(request)
        if not approvers:
            raise ValidationFailed("No team leader is set up for this team. Ask an administrator.")

        change = RequestChange(
            requested_by_id=user.id,
            requested_by=user,
            status=ChangeStatus.PENDING.value,
            reason=reason,
            old_start=request.planned_start,
            old_end=request.planned_end,
            old_headcount=request.headcount,
            new_start=new_start,
            new_end=new_end,
            new_headcount=new_headcount,
        )
        request.changes.append(change)
        self.s.flush()
        due = self.ctx.clock.now() + timedelta(
            days=(
                self.ctx.calendar.add_working_days(today, self.ctx.config.get_int("tl_due_working_days"))
                - today
            ).days
        )
        change_tasks = []
        for approver in approvers:
            change_tasks.append(
                ApprovalTask(
                    round=request.round,
                    step=ApprovalStep.CHANGE_REVIEW.value,
                    assignee_id=approver.id,
                    assignee=approver,
                    status=TaskStatus.PENDING.value,
                    due_at=due,
                    change_id=change.id,
                )
            )
        request.tasks.extend(change_tasks)
        self.s.flush()
        summary = self.describe_change(change)
        self._event(request, user, "CHANGE_REQUEST", request.status, reason, {"change": summary})
        self.notify_tasks(
            Event.CHANGE_REQUESTED,
            request,
            change_tasks,
            actor=user,
            cc=[user],
            comment=reason,
            extra={"change": summary},
        )
        return change

    def decide_change(
        self,
        user: User,
        request: ResourceRequest,
        change_id: int,
        action: Action,
        *,
        comment: str | None,
        allocations: list[AllocationSpec] | None = None,
        via: str | None = None,
        client: dict[str, str] | None = None,
    ) -> RequestChange:
        """The team leader approves (with the final list of engineers) or rejects a change."""
        change = next((c for c in request.changes if c.id == change_id), None)
        if change is None:
            raise ValidationFailed(
                "This change belongs to a different request. Refresh the page and try again."
            )
        if change.status != ChangeStatus.PENDING.value:
            raise Conflict("This change has already been handled. Refresh the page to see its outcome.")
        if action not in (Action.APPROVE, Action.REJECT):
            raise ValidationFailed("Choose approve or reject.")
        task = next(
            (
                t
                for t in request.tasks
                if t.change_id == change.id
                and t.assignee_id == user.id
                and t.status == TaskStatus.PENDING.value
            ),
            None,
        )
        if task is None:
            raise Forbidden("This change is not waiting for your decision.")
        comment = (comment or "").strip() or None
        now = self.ctx.clock.now()
        summary = self.describe_change(change)

        if action == Action.REJECT:
            if not comment:
                raise ValidationFailed(
                    "Add a comment that explains why the change is rejected.",
                    details={"fields": {"comment": "A comment is required."}},
                )
            change.status = ChangeStatus.REJECTED.value
            task.status = TaskStatus.REJECTED.value
        else:
            specs = self._specs(None, allocations)
            self._check_allocation(request, specs, change.new_headcount, comment)
            before_allocations = list(self._active_allocations(request))
            before = {a.engineer_id for a in before_allocations}
            request.planned_start = change.new_start
            request.planned_end = change.new_end
            request.headcount = change.new_headcount
            names = self._set_allocations(
                user, request, specs, AllocationStatus.CONFIRMED, change.new_start, change.new_end
            )
            removed_allocations = [
                a for a in before_allocations if a.status == AllocationStatus.RELEASED.value
            ]
            change.status = ChangeStatus.APPROVED.value
            task.status = TaskStatus.APPROVED.value

        change.decided_by_id = user.id
        change.decided_by = user
        change.decision_comment = comment
        change.decided_at = now
        task.decision_comment = comment
        task.acted_at = now
        for other in request.tasks:
            if other.change_id == change.id and other.status == TaskStatus.PENDING.value:
                other.status = TaskStatus.CLOSED.value
                other.acted_at = now
        self.s.flush()

        if action == Action.REJECT:
            self._event(
                request,
                user,
                "CHANGE_REJECT",
                request.status,
                comment,
                {
                    "change": summary,
                    **({"via": via} if via else {}),
                    **({"client": client} if client else {}),
                },
            )
            self.notifications.notify(
                Event.CHANGE_REJECTED,
                request,
                to=[request.requester],
                cc=[user],
                actor=user,
                comment=comment,
                extra={"change": summary},
            )
        else:
            self._event(
                request,
                user,
                "CHANGE_APPROVE",
                request.status,
                comment,
                {
                    "change": summary,
                    "engineers": names,
                    **({"via": via} if via else {}),
                    **({"client": client} if client else {}),
                },
            )
            sequence = self._calendar_sequence(request)
            active = self._active_allocations(request)
            kept = [a for a in active if a.engineer_id in before]
            added = [a for a in active if a.engineer_id not in before]
            change_extra = {"change": summary}
            no_invite = self._send_assignments(
                request, kept, Event.ASSIGNMENT_UPDATED, actor=user, sequence=sequence, extra=change_extra
            )
            no_invite += self._send_assignments(
                request, added, Event.ASSIGNMENT_INVITE, actor=user, sequence=sequence, extra=change_extra
            )
            no_invite += self._send_assignments(
                request,
                removed_allocations,
                Event.ASSIGNMENT_CANCELLED,
                actor=user,
                sequence=sequence,
                extra={**change_extra, "reason": "the team leader changed the engineers for the new period"},
            )
            self.notifications.notify(
                Event.CHANGE_APPROVED,
                request,
                to=[request.requester, *no_invite],
                cc=self._team_approvers(request),
                actor=user,
                comment=comment,
                extra=change_extra,
            )
        return change

    def withdraw_change(self, user: User, request: ResourceRequest, change_id: int) -> RequestChange:
        change = next((c for c in request.changes if c.id == change_id), None)
        if change is None or change.status != ChangeStatus.PENDING.value:
            raise Conflict("This change is no longer waiting for review.")
        if change.requested_by_id != user.id:
            raise Forbidden("Only the person who asked for the change can withdraw it.")
        now = self.ctx.clock.now()
        change.status = ChangeStatus.WITHDRAWN.value
        change.decided_at = now
        for t in request.tasks:
            if t.change_id == change.id and t.status == TaskStatus.PENDING.value:
                t.status = TaskStatus.CLOSED.value
                t.acted_at = now
        self.s.flush()
        self._event(
            request, user, "CHANGE_WITHDRAW", request.status, None, {"change": self.describe_change(change)}
        )
        return change

    # ------------------------------------------------------------------ approver changes

    def reassign_team_reviews(self, actor: User, team_id: int, approvers: Sequence[User]) -> int:
        """Move open team-leader reviews of a team to its current approvers.

        Review tasks are created when a request (or a change) is submitted. When an administrator changes
        a team's approvers later, waiting requests would otherwise stay with the previous approvers.
        Returns the number of requests whose reviewers changed."""
        wanted = {u.id: u for u in approvers}
        steps = (ApprovalStep.TL_REVIEW.value, ApprovalStep.CHANGE_REVIEW.value)
        pending = self.s.scalars(
            select(ApprovalTask)
            .join(ResourceRequest, ApprovalTask.request_id == ResourceRequest.id)
            .where(
                ApprovalTask.status == TaskStatus.PENDING.value,
                ApprovalTask.step.in_(steps),
                ResourceRequest.team_id == team_id,
            )
        ).all()
        groups: dict[tuple[int, str, int | None], list[ApprovalTask]] = {}
        for task in pending:
            groups.setdefault((task.request_id, task.step, task.change_id), []).append(task)

        now = self.ctx.clock.now()
        changed = 0
        for tasks in groups.values():
            request = tasks[0].request
            current = {t.assignee_id for t in tasks}
            removed = [t for t in tasks if t.assignee_id not in wanted]
            added = [u for uid, u in wanted.items() if uid not in current]
            if not removed and not added:
                continue
            for t in removed:
                t.status = TaskStatus.CLOSED.value
                t.acted_at = now
            template = tasks[0]
            new_tasks = []
            for user in added:
                new_tasks.append(
                    ApprovalTask(
                        round=template.round,
                        step=template.step,
                        assignee_id=user.id,
                        assignee=user,
                        status=TaskStatus.PENDING.value,
                        due_at=template.due_at,
                        change_id=template.change_id,
                    )
                )
            request.tasks.extend(new_tasks)
            self.s.flush()
            self._event(
                request,
                actor,
                "REASSIGN",
                request.status,
                None,
                {
                    "step": template.step,
                    "added": [u.display_name for u in added],
                    "removed": [t.assignee.display_name for t in removed],
                },
            )
            if added:
                change = next((c for c in request.changes if c.id == template.change_id), None)
                if change is not None:
                    self.notify_tasks(
                        Event.CHANGE_REQUESTED,
                        request,
                        new_tasks,
                        actor=change.requested_by,
                        comment=change.reason,
                        extra={"change": self.describe_change(change)},
                    )
                else:
                    self.notify_tasks(Event.REQUEST_SUBMITTED, request, new_tasks, actor=request.requester)
            changed += 1
        return changed
