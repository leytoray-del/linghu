"""Withdrawals: taking items of one project out of stock to a new location.

Flow: the requester submits; the PM named on the project approves; then anyone with the Operations
manager role approves; on that final approval the items move to the new location and become deployed.
Rejecting at either step sends the request back to the requester, who can revise and resubmit it, or
withdraw it. Nobody approves their own request: when the requester is the project's PM, the PM step is
skipped and recorded.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select

from erf.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from erf.db.models import Location, User, UserRole
from erf.domain.enums import LocationKind, Role
from erf.domain.permissions import Permission, permissions_for
from erf.modules.inventory.domain import (
    OPEN_WITHDRAWAL,
    FieldDef,
    ItemStatus,
    MovementKind,
    WithdrawalStatus,
    WithdrawalStep,
)
from erf.modules.inventory.models import (
    InvItem,
    InvMovement,
    InvWithdrawal,
    InvWithdrawalEvent,
    InvWithdrawalItem,
    InvWithdrawalTask,
)
from erf.modules.inventory.notify import WithdrawalMail
from erf.modules.inventory.schemas import (
    WithdrawalDecisionIn,
    WithdrawalDetailOut,
    WithdrawalEventOut,
    WithdrawalIn,
    WithdrawalOut,
    WithdrawalReviseIn,
    WithdrawalTaskOut,
    WithdrawalVersionIn,
)
from erf.modules.inventory.service import item_out
from erf.repositories.settings import SettingsRepository
from erf.services.context import ServiceContext
from erf.services.org_service import OrgService, location_out, project_out
from erf.services.presenters import user_ref

PENDING_STEP = {
    WithdrawalStatus.PENDING_PM: WithdrawalStep.PM,
    WithdrawalStatus.PENDING_OM: WithdrawalStep.OM,
}
DEPLOYMENT_DATE_KEY = "deployment_date"


class WithdrawalService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.mail = WithdrawalMail(ctx)

    # ---- who decides --------------------------------------------------------------------

    def operations_managers(self) -> list[User]:
        return list(
            self.s.scalars(
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role == Role.OPS_MANAGER.value, User.is_active.is_(True))
                .order_by(User.display_name)
            )
        )

    def approvers(self, w: InvWithdrawal, step: WithdrawalStep) -> list[User]:
        if step == WithdrawalStep.PM:
            pm = w.project.pm
            return [pm] if pm and pm.is_active else []
        return [u for u in self.operations_managers() if u.id != w.requester_id]

    def _current_task(self, w: InvWithdrawal) -> InvWithdrawalTask | None:
        return next((t for t in w.tasks if t.round == w.round and t.status == "PENDING"), None)

    def _can_decide(self, user: User, w: InvWithdrawal) -> bool:
        step = PENDING_STEP.get(WithdrawalStatus(w.status))
        return (
            step is not None
            and user.id != w.requester_id
            and any(u.id == user.id for u in self.approvers(w, step))
        )

    # ---- reading ------------------------------------------------------------------------

    def _get(self, withdrawal_id: int) -> InvWithdrawal:
        w = self.s.get(InvWithdrawal, withdrawal_id)
        if w is None:
            raise NotFound("This withdrawal request does not exist.")
        return w

    def _may_see(self, user: User, w: InvWithdrawal) -> bool:
        return (
            w.requester_id == user.id
            or w.project.pm_user_id == user.id
            or user.has_role(Role.OPS_MANAGER)
            or Permission.INVENTORY_WITHDRAWALS_ALL in permissions_for(user.roles)
        )

    def out(self, w: InvWithdrawal) -> WithdrawalOut:
        step = PENDING_STEP.get(WithdrawalStatus(w.status))
        return WithdrawalOut(
            id=w.id,
            request_no=w.request_no,
            project=project_out(w.project),
            requester=user_ref(w.requester),
            to_location=location_out(w.to_location),
            reason=w.reason,
            status=WithdrawalStatus(w.status),
            item_count=len(w.lines),
            submitted_at=w.submitted_at,
            completed_at=w.completed_at,
            waiting_for=[user_ref(u) for u in self.approvers(w, step)] if step else [],
            version=w.version,
        )

    def detail(self, user: User, withdrawal_id: int) -> WithdrawalDetailOut:
        w = self._get(withdrawal_id)
        if not self._may_see(user, w):
            raise Forbidden("You do not have access to this withdrawal request.")
        events = self.s.scalars(
            select(InvWithdrawalEvent)
            .where(InvWithdrawalEvent.withdrawal_id == w.id)
            .order_by(InvWithdrawalEvent.occurred_at.desc(), InvWithdrawalEvent.id.desc())
        )
        tasks = [
            WithdrawalTaskOut(
                round=t.round,
                step=WithdrawalStep(t.step),
                status=t.status,
                approvers=[user_ref(u) for u in self.approvers(w, WithdrawalStep(t.step))]
                if t.status == "PENDING"
                else [],
                decided_by=user_ref(t.decided_by) if t.decided_by else None,
                comment=t.comment,
                decided_at=t.decided_at,
            )
            for t in w.tasks
            if t.round == w.round
        ]
        status = WithdrawalStatus(w.status)
        return WithdrawalDetailOut(
            **self.out(w).model_dump(),
            items=[item_out(line.item) for line in sorted(w.lines, key=lambda x: x.item.serial_no)],
            tasks=tasks,
            events=[
                WithdrawalEventOut(
                    action=e.action, actor=user_ref(e.actor), comment=e.comment, occurred_at=e.occurred_at
                )
                for e in events
            ],
            can_decide=self._can_decide(user, w),
            can_revise=w.requester_id == user.id and status == WithdrawalStatus.RETURNED,
            can_withdraw=w.requester_id == user.id and status in OPEN_WITHDRAWAL,
        )

    def list_requests(
        self, user: User, scope: str, statuses: Sequence[WithdrawalStatus] = ()
    ) -> list[WithdrawalOut]:
        q = select(InvWithdrawal).order_by(InvWithdrawal.submitted_at.desc(), InvWithdrawal.id.desc())
        if statuses:
            q = q.where(InvWithdrawal.status.in_([s.value for s in statuses]))
        rows = list(self.s.scalars(q.limit(500)))
        if scope == "mine":
            rows = [w for w in rows if w.requester_id == user.id]
        elif scope == "waiting":
            rows = [w for w in rows if self._can_decide(user, w)]
        else:
            rows = [w for w in rows if self._may_see(user, w)]
        return [self.out(w) for w in rows]

    def pending_count(self, user: User) -> int:
        q = select(InvWithdrawal).where(
            InvWithdrawal.status.in_([WithdrawalStatus.PENDING_PM.value, WithdrawalStatus.PENDING_OM.value])
        )
        return sum(1 for w in self.s.scalars(q) if self._can_decide(user, w))

    # ---- changes ------------------------------------------------------------------------

    def _event(self, w: InvWithdrawal, user: User, action: str, comment: str | None = None) -> None:
        self.s.add(
            InvWithdrawalEvent(
                withdrawal_id=w.id,
                action=action,
                actor_id=user.id,
                comment=comment,
                occurred_at=self.ctx.clock.now(),
            )
        )

    def _move(self, item: InvItem, user: User, kind: MovementKind, w: InvWithdrawal, **values: Any) -> None:
        self.s.add(
            InvMovement(
                item_id=item.id,
                kind=kind.value,
                actor_id=user.id,
                withdrawal_id=w.id,
                occurred_at=self.ctx.clock.now(),
                **values,
            )
        )

    def _check(
        self, user: User, data: WithdrawalIn, current: InvWithdrawal | None = None
    ) -> tuple[list[InvItem], Location]:
        org = OrgService(self.ctx)
        project = org.project(data.project_id)
        problems: dict[str, str] = {}
        if not project.is_active:
            problems["project_id"] = "This project is closed."
        location = self.s.get(Location, data.to_location_id)
        if location is None or not location.is_active:
            problems["to_location_id"] = "Choose the new location."
        reason = data.reason.strip()
        if not reason:
            problems["reason"] = "Explain what the items are needed for."
        ids = list(dict.fromkeys(data.item_ids))
        items = list(self.s.scalars(select(InvItem).where(InvItem.id.in_(ids))))
        mine = {line.item_id for line in current.lines} if current else set()
        bad: list[str] = []
        for i in items:
            if i.deleted_at is not None:
                bad.append(f"{i.serial_no} has been deleted")
            elif i.project_id != project.id:
                bad.append(f"{i.serial_no} belongs to {i.project.name}")
            elif i.status != ItemStatus.IN_STOCK.value and i.id not in mine:
                bad.append(f"{i.serial_no} is not in stock")
        if len(items) != len(ids):
            bad.append("some items no longer exist")
        if bad:
            problems["item_ids"] = "These items cannot be requested: " + "; ".join(bad) + "."
        if location is not None and any(i.location_id == location.id for i in items):
            problems.setdefault(
                "to_location_id", "Some items are already at this location. Choose where they are going."
            )
        if problems:
            raise ValidationFailed(next(iter(problems.values())), details={"fields": problems})
        if project.pm is None and project.pm_user_id != user.id:
            raise ValidationFailed(
                f"{project.name} has no project manager, so nobody can give the first approval. Ask an administrator to set the PM."
            )
        if not [u for u in self.operations_managers() if u.id != user.id]:
            raise ValidationFailed(
                "No operations manager is set up to give the final approval. Ask an administrator."
            )
        return items, location  # type: ignore[return-value]

    def _start_round(self, user: User, w: InvWithdrawal) -> None:
        """Create the approval steps of the current round and notify the first approver."""
        now = self.ctx.clock.now()
        if w.project.pm_user_id == user.id:
            self.s.add(
                InvWithdrawalTask(
                    withdrawal_id=w.id, round=w.round, step=WithdrawalStep.PM.value, status="SKIPPED",
                    comment="The requester is the project's PM.", created_at=now, decided_at=now,
                )
            )  # fmt: skip
            w.status = WithdrawalStatus.PENDING_OM.value
            self.s.add(
                InvWithdrawalTask(
                    withdrawal_id=w.id,
                    round=w.round,
                    step=WithdrawalStep.OM.value,
                    status="PENDING",
                    created_at=now,
                )
            )
        else:
            w.status = WithdrawalStatus.PENDING_PM.value
            self.s.add(
                InvWithdrawalTask(
                    withdrawal_id=w.id,
                    round=w.round,
                    step=WithdrawalStep.PM.value,
                    status="PENDING",
                    created_at=now,
                )
            )
        self.s.flush()
        self.s.refresh(w)
        step = PENDING_STEP[WithdrawalStatus(w.status)]
        self.mail.waiting(w, self.approvers(w, step), step)

    def _request_items(self, user: User, w: InvWithdrawal, items: list[InvItem]) -> None:
        for i in items:
            before = i.status
            i.status = ItemStatus.REQUESTED.value
            self._move(i, user, MovementKind.REQUEST, w, from_status=before, to_status=i.status)

    def _release_items(self, user: User, w: InvWithdrawal, reason: str | None) -> None:
        for line in w.lines:
            i = line.item
            if i.status == ItemStatus.REQUESTED.value:
                i.status = ItemStatus.IN_STOCK.value
                self._move(
                    i,
                    user,
                    MovementKind.RELEASE,
                    w,
                    from_status=ItemStatus.REQUESTED.value,
                    to_status=i.status,
                    reason=reason,
                )

    def create(self, user: User, data: WithdrawalIn) -> WithdrawalDetailOut:
        items, location = self._check(user, data)
        now = self.ctx.clock.now()
        year = self.ctx.clock.today().year
        number = SettingsRepository(self.s).next_sequence("WDR", year)
        w = InvWithdrawal(
            request_no=f"WDR-{year}-{number:04d}",
            project_id=data.project_id,
            requester_id=user.id,
            to_location_id=location.id,
            reason=data.reason.strip(),
            status=WithdrawalStatus.PENDING_PM.value,
            round=1,
            submitted_at=now,
        )
        self.s.add(w)
        self.s.flush()
        for i in items:
            self.s.add(InvWithdrawalItem(withdrawal_id=w.id, item_id=i.id))
        self._request_items(user, w, items)
        self._event(w, user, "SUBMIT")
        self.s.flush()
        self.s.refresh(w)
        self._start_round(user, w)
        return self.detail(user, w.id)

    def _check_version(self, w: InvWithdrawal, version: int) -> None:
        if w.version != version:
            raise Conflict(
                "Someone else changed this request after you opened it. Refresh the page and try again."
            )

    def decide(self, user: User, withdrawal_id: int, data: WithdrawalDecisionIn) -> WithdrawalDetailOut:
        w = self._get(withdrawal_id)
        self._check_version(w, data.version)
        if not self._can_decide(user, w):
            raise Forbidden("This request is not waiting for your decision.")
        task = self._current_task(w)
        assert task is not None
        comment = (data.comment or "").strip() or None
        now = self.ctx.clock.now()
        step = WithdrawalStep(task.step)
        if not data.approve:
            if not comment:
                raise ValidationFailed(
                    "Add a comment so the requester knows what to change.",
                    details={"fields": {"comment": "A comment is required."}},
                )
            task.status, task.decided_by_id, task.comment, task.decided_at = "REJECTED", user.id, comment, now
            w.status = WithdrawalStatus.RETURNED.value
            self._release_items(user, w, f"Rejected: {comment}")
            self._event(w, user, f"REJECT_{step.value}", comment)
            self.s.flush()
            self.mail.rejected(w, user, comment)
            return self.detail(user, w.id)

        task.status, task.decided_by_id, task.comment, task.decided_at = "APPROVED", user.id, comment, now
        self._event(w, user, f"APPROVE_{step.value}", comment)
        if step == WithdrawalStep.PM:
            w.status = WithdrawalStatus.PENDING_OM.value
            self.s.add(
                InvWithdrawalTask(
                    withdrawal_id=w.id,
                    round=w.round,
                    step=WithdrawalStep.OM.value,
                    status="PENDING",
                    created_at=now,
                )
            )
            self.s.flush()
            self.s.refresh(w)
            self.mail.waiting(w, self.approvers(w, WithdrawalStep.OM), WithdrawalStep.OM)
            return self.detail(user, w.id)

        # Final approval: the items move to the new location.
        today = self.ctx.clock.today().isoformat()
        for line in w.lines:
            i = line.item
            before_location = i.location_id
            i.status = ItemStatus.DEPLOYED.value
            i.location_id = w.to_location_id
            fields = {FieldDef.model_validate(f).key for f in i.category.fields or []}
            if DEPLOYMENT_DATE_KEY in fields and not (i.attributes or {}).get(DEPLOYMENT_DATE_KEY):
                i.attributes = {**(i.attributes or {}), DEPLOYMENT_DATE_KEY: today}
            self._move(
                i, user, MovementKind.DEPLOY, w,
                from_status=ItemStatus.REQUESTED.value, to_status=i.status,
                from_location_id=before_location, to_location_id=w.to_location_id,
            )  # fmt: skip
        w.status = WithdrawalStatus.APPROVED.value
        w.completed_at = now
        self.s.flush()
        # Reload the items so their new location is shown, not the one loaded before the change.
        for line in w.lines:
            self.s.refresh(line.item)
        self.mail.approved(w, user)
        return self.detail(user, w.id)

    def revise(self, user: User, withdrawal_id: int, data: WithdrawalReviseIn) -> WithdrawalDetailOut:
        w = self._get(withdrawal_id)
        self._check_version(w, data.version)
        if w.requester_id != user.id or w.status != WithdrawalStatus.RETURNED.value:
            raise Forbidden("Only the requester can revise a request that was sent back.")
        if data.project_id != w.project_id:
            raise ValidationFailed(
                "A request stays with its project. Start a new request for another project."
            )
        items, location = self._check(user, data, w)
        w.lines = [InvWithdrawalItem(item_id=i.id) for i in items]
        w.to_location_id = location.id
        w.reason = data.reason.strip()
        w.round += 1
        w.submitted_at = self.ctx.clock.now()
        self.s.flush()
        self._request_items(user, w, items)
        self._event(w, user, "RESUBMIT")
        self.s.flush()
        self.s.refresh(w)
        self._start_round(user, w)
        return self.detail(user, w.id)

    def withdraw(self, user: User, withdrawal_id: int, data: WithdrawalVersionIn) -> WithdrawalDetailOut:
        w = self._get(withdrawal_id)
        self._check_version(w, data.version)
        if w.requester_id != user.id or WithdrawalStatus(w.status) not in OPEN_WITHDRAWAL:
            raise Forbidden("Only the requester can withdraw an open request.")
        comment = (data.comment or "").strip() or None
        for t in w.tasks:
            if t.status == "PENDING":
                t.status = "CLOSED"
        self._release_items(user, w, "The request was withdrawn.")
        w.status = WithdrawalStatus.WITHDRAWN.value
        w.completed_at = self.ctx.clock.now()
        self._event(w, user, "WITHDRAW", comment)
        self.s.flush()
        return self.detail(user, w.id)

    def add_site(self, user: User, name: str) -> Location:
        """Add a site that is not in the location list yet, while requesting a withdrawal."""
        clean = " ".join(name.split())
        existing = self.s.scalar(select(Location).where(func.lower(Location.name) == clean.lower()))
        if existing is not None:
            if not existing.is_active:
                raise ValidationFailed(
                    f"{existing.name} exists but is inactive. Ask an administrator to reactivate it."
                )
            return existing
        loc = Location(name=clean, kind=LocationKind.SITE.value, is_active=True)
        self.s.add(loc)
        self.s.flush()
        return loc
