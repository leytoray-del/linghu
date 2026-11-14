"""Who may see and act on what. All authorisation decisions go through this module."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.orm import Session

from erf.core.errors import Forbidden
from erf.db.models import ResourceRequest, User
from erf.domain.enums import AllocationStatus, RequestStatus, Role, TaskStatus
from erf.domain.permissions import Permission
from erf.domain.workflow import STEP_FOR_STATUS, Actor
from erf.repositories.users import TeamRepository
from erf.services.permission_service import can


class ListScope(StrEnum):
    MINE = "mine"
    """Requests I raised."""
    TEAM = "team"
    """Requests routed to teams I review."""
    ALL = "all"
    """Every submitted request (director, administrator, viewer)."""
    ASSIGNED = "assigned"
    """Requests I am allocated to as an engineer."""


class AccessPolicy:
    def __init__(self, session: Session):
        self.s = session
        self._led: dict[int, list[int]] = {}

    def led_team_ids(self, user: User) -> list[int]:
        if user.id not in self._led:
            self._led[user.id] = TeamRepository(self.s).teams_led_by(user.id)
        return self._led[user.id]

    def allowed_scopes(self, user: User) -> list[ListScope]:
        scopes = [ListScope.MINE]
        if self.led_team_ids(user):
            scopes.append(ListScope.TEAM)
        if can(self.s, user, Permission.RESOURCES_OVERVIEW):
            scopes.append(ListScope.ALL)
        if user.has_role(Role.ENGINEER):
            scopes.append(ListScope.ASSIGNED)
        return scopes

    def require_scope(self, user: User, scope: ListScope) -> None:
        if scope not in self.allowed_scopes(user):
            raise Forbidden("You do not have access to that list.")

    def can_view(self, user: User, request: ResourceRequest) -> bool:
        if request.requester_id == user.id:
            return True
        if request.status == RequestStatus.DRAFT.value:
            return False
        if can(self.s, user, Permission.RESOURCES_OVERVIEW):
            return True
        if request.team_id is not None and request.team_id in self.led_team_ids(user):
            return True
        if any(t.assignee_id == user.id for t in request.tasks):
            return True
        return any(
            a.engineer_id == user.id and a.status != AllocationStatus.RELEASED.value
            for a in request.allocations
        )

    def require_view(self, user: User, request: ResourceRequest) -> None:
        if not self.can_view(user, request):
            raise Forbidden("You do not have access to this request.")

    def capacities(self, user: User, request: ResourceRequest) -> set[Actor]:
        caps: set[Actor] = set()
        if request.requester_id == user.id:
            caps.add(Actor.REQUESTER)
        if user.has_role(Role.ADMIN):
            caps.add(Actor.ADMIN)
        step = STEP_FOR_STATUS.get(request.status_enum)
        if step is not None and any(
            t.assignee_id == user.id
            and t.status == TaskStatus.PENDING.value
            and t.step == step.value
            and t.round == request.round
            for t in request.tasks
        ):
            caps.add(Actor.STEP_ASSIGNEE)
        return caps

    def can_plan_resources(self, user: User, team_id: int | None) -> bool:
        if user.has_role(Role.DIRECTOR, Role.ADMIN):
            return True
        return team_id is not None and team_id in self.led_team_ids(user)
