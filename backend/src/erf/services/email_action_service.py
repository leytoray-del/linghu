"""Approve, return and reject from an email: reads a signed link and acts as the approver it belongs to.

Opening a link only shows a confirmation page (GET). The decision happens when the approver confirms
(POST). Email security scanners open links automatically, so nothing may change on GET.
"""

from __future__ import annotations

from datetime import UTC, datetime

from erf.core.action_tokens import read_token
from erf.core.errors import Conflict, Gone, NotFound, ValidationFailed
from erf.db.models import ApprovalTask
from erf.domain.enums import Action, ApprovalStep, TaskStatus
from erf.schemas.requests import (
    AllocationIn,
    EmailActionOut,
    EmailActionResult,
)
from erf.services import presenters
from erf.services.action_links import action_secret
from erf.services.context import ServiceContext
from erf.services.request_service import RequestService
from erf.services.resource_service import ResourceService
from erf.services.workflow_service import WorkflowService

STATUS_TEXT = {
    "PENDING_TL_REVIEW": "waiting for the team leader",
    "PENDING_DIRECTOR_APPROVAL": "waiting for the director",
    "APPROVED": "approved",
    "RETURNED": "rejected and sent back to the requester",
    "REJECTED": "rejected permanently",
    "WITHDRAWN": "withdrawn",
    "CANCELLED": "cancelled",
    "CLOSED": "closed",
}


class EmailActionService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session

    def _task(self, token: str) -> tuple[ApprovalTask, datetime]:
        data = read_token(action_secret(self.ctx), token)
        task = self.s.get(ApprovalTask, data.task_id) if data else None
        if data is None or task is None:
            raise NotFound("This link is not valid. Open the request in the system instead.")
        expires = datetime.fromtimestamp(data.expires, UTC).replace(tzinfo=None)
        if expires < self.ctx.clock.now():
            raise Gone(
                "This link has expired. Open the request in the system to act on it.", code="link_expired"
            )
        if task.status != TaskStatus.PENDING.value:
            r = task.request
            raise Conflict(
                f"{r.display_no} no longer needs your decision. It is now {STATUS_TEXT.get(r.status, r.status.lower())}.",
                code="already_handled",
                details={"request_id": r.id, "status": r.status},
            )
        if not task.assignee.is_active:
            raise Gone("This link belongs to an account that is no longer active.", code="link_expired")
        return task, expires

    def view(self, token: str) -> EmailActionOut:
        task, expires = self._task(token)
        r = task.request
        user = task.assignee
        detail = RequestService(self.ctx).to_detail(user, r)
        change = next((c for c in detail.changes if c.id == task.change_id), None) if task.change_id else None
        candidates = []
        preselected: list[AllocationIn] = []
        resources = ResourceService(self.ctx)
        if task.step == ApprovalStep.TL_REVIEW.value:
            candidates = resources.candidates(user, r.id)
            preselected = [
                AllocationIn(engineer_id=c.engineer.id, allocation_pct=100)
                for c in candidates
                if c.is_preferred
            ]
        elif task.step == ApprovalStep.CHANGE_REVIEW.value and change is not None:
            candidates = resources.candidates(user, r.id, change.new_start, change.new_end)
            preselected = [
                AllocationIn(engineer_id=a.engineer.id, allocation_pct=a.allocation_pct)
                for a in detail.allocations
            ]
        actions = (
            [Action.APPROVE, Action.REJECT]
            if task.step == ApprovalStep.CHANGE_REVIEW.value
            else [Action.APPROVE, Action.RETURN]
        )
        return EmailActionOut(
            step=task.step,
            assignee=presenters.user_ref(user),
            expires_at=expires,
            actions=actions,
            request=detail,
            change=change,
            candidates=candidates,
            preselected=preselected,
        )

    def act(
        self,
        token: str,
        action: Action,
        comment: str | None,
        allocations: list[AllocationIn],
        client: dict[str, str] | None = None,
    ) -> EmailActionResult:
        task, _ = self._task(token)
        r = task.request
        user = task.assignee
        specs = [(a.engineer_id, a.allocation_pct) for a in allocations]
        workflow = WorkflowService(self.ctx)
        if task.step == ApprovalStep.CHANGE_REVIEW.value:
            if action not in (Action.APPROVE, Action.REJECT):
                raise ValidationFailed("A change can only be approved or rejected.")
            assert task.change_id is not None
            workflow.decide_change(
                user,
                r,
                task.change_id,
                action,
                comment=comment,
                allocations=specs,
                via="email",
                client=client,
            )
            message = (
                f"The change to {r.display_no} was {'approved' if action == Action.APPROVE else 'rejected'}."
            )
        else:
            if action == Action.REJECT:
                raise ValidationFailed(
                    "A request can only be rejected permanently in the system. Sign in to do this."
                )
            workflow.decide(
                user,
                r,
                action,
                comment=comment,
                version=None,
                allocations=specs if action == Action.APPROVE else None,
                via="email",
                client=client,
            )
            done = {
                Action.APPROVE: "approved",
                Action.RETURN: "rejected and sent back to the requester, who can revise and resubmit it",
                Action.REJECT: "rejected permanently",
            }[action]
            message = f"{r.display_no} was {done}."
            if r.status == "PENDING_DIRECTOR_APPROVAL":
                message += " It is now with the director for final approval."
        return EmailActionResult(
            message=message, request_id=r.id, display_no=r.display_no, status=r.status_enum
        )
