"""Applies state-machine transitions: tasks, allocations, audit events and notifications.

Every method runs inside the caller's unit of work, so a transition and everything it causes
(including queued emails) is committed together or not at all.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from erf.core.errors import Conflict, Forbidden, ValidationFailed
from erf.db.models import ApprovalTask, RequestEvent, ResourceAllocation, ResourceRequest, User
from erf.domain.enums import (
    Action,
    AllocationStatus,
    ApprovalStep,
    Priority,
    RequestStatus,
    RequestType,
    Role,
    TaskStatus,
)
from erf.domain.urgency import evaluate_urgency
from erf.domain.validation import SubmissionFields, validate_submission
from erf.domain.workflow import STEP_FOR_STATUS, Actor, Transition, find_transition
from erf.repositories.settings import SupportTypeRepository
from erf.repositories.users import TeamRepository, UserRepository
from erf.services.access import AccessPolicy
from erf.services.context import ServiceContext
from erf.services.notifications import Event, NotificationService

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
            raise Forbidden("This action needs a signed-in user.")
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

    def _create_tasks(self, request: ResourceRequest, step: ApprovalStep, assignees: Sequence[User]) -> None:
        due = self._due_at(request, step)
        for user in assignees:
            request.tasks.append(
                ApprovalTask(
                    round=request.round,
                    step=step.value,
                    assignee_id=user.id,
                    assignee=user,
                    status=TaskStatus.PENDING.value,
                    due_at=due,
                )
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
        self._create_tasks(request, ApprovalStep.TL_REVIEW, approvers)
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
        self.notifications.notify(Event.REQUEST_SUBMITTED, request, to=approvers, cc=[user], actor=user)
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
    ) -> ResourceRequest:
        if action not in TASK_RESULT:
            raise ValidationFailed("Choose approve, return or reject.")
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
            allocation_names = self._propose_allocations(user, request, engineer_ids or [], comment)

        from_status = request.status
        now = self.ctx.clock.now()
        task.status = TASK_RESULT[action].value
        task.decision_comment = comment
        task.acted_at = now
        self._close_pending_tasks(request, except_task=task)
        request.status = transition.target.value

        payload: dict[str, Any] = {"step": step.value, "round": request.round}
        if allocation_names:
            payload["engineers"] = allocation_names

        if transition.target == RequestStatus.PENDING_DIRECTOR_APPROVAL:
            directors = self.directors()
            if not directors:
                raise ValidationFailed("No director is set up to give final approval. Ask an administrator.")
            self._create_tasks(request, ApprovalStep.DIRECTOR_APPROVAL, directors)
            self.s.flush()
            self._event(request, user, "TL_APPROVE", from_status, comment, payload)
            self.notifications.notify(
                Event.TL_APPROVED, request, to=directors, cc=[request.requester], actor=user, comment=comment
            )
        elif transition.target == RequestStatus.APPROVED:
            for a in self._active_allocations(request):
                a.status = AllocationStatus.CONFIRMED.value
            request.decided_at = now
            self.s.flush()
            engineers = [a.engineer for a in self._active_allocations(request)]
            self._event(request, user, "DIRECTOR_APPROVE", from_status, comment, payload)
            self.notifications.notify(
                Event.REQUEST_APPROVED,
                request,
                to=[request.requester, *engineers],
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

    def _propose_allocations(
        self, user: User, request: ResourceRequest, engineer_ids: list[int], comment: str | None
    ) -> list[str]:
        unique_ids = list(dict.fromkeys(engineer_ids))
        if not unique_ids:
            raise ValidationFailed(
                "Assign at least one engineer before approving.",
                details={"fields": {"engineer_ids": "Select at least one engineer."}},
            )
        engineers = {u.id: u for u in self.users.get_many(unique_ids)}
        problems = [
            i
            for i in unique_ids
            if i not in engineers
            or not engineers[i].is_active
            or not engineers[i].has_role(Role.ENGINEER)
            or engineers[i].team_id != request.team_id
        ]
        if problems:
            raise ValidationFailed(
                "Some selected people are not active engineers in this team.",
                details={
                    "fields": {"engineer_ids": "Choose engineers from the team that handles this request."}
                },
            )
        if request.headcount and len(unique_ids) < request.headcount and not comment:
            raise ValidationFailed(
                f"You assigned {len(unique_ids)} of {request.headcount} requested engineers. "
                "Add a comment that explains the shortfall.",
                details={"fields": {"comment": "Explain why fewer engineers are assigned."}},
            )
        self._release_allocations(request)
        assert request.planned_start and request.planned_end
        for i in unique_ids:
            request.allocations.append(
                ResourceAllocation(
                    engineer_id=i,
                    engineer=engineers[i],
                    start_date=request.planned_start,
                    end_date=request.planned_end,
                    status=AllocationStatus.PROPOSED.value,
                    allocated_by_id=user.id,
                )
            )
        self.s.flush()
        return [engineers[i].display_name for i in unique_ids]

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
        released = self._release_allocations(request)
        request.status = transition.target.value
        self.s.flush()
        self._event(request, user, "CANCEL", from_status, comment)
        self.notifications.notify(
            Event.REQUEST_CANCELLED,
            request,
            to=[*released, *self._team_approvers(request)],
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
