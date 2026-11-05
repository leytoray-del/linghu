"""Engineer availability: allocation candidates for a request and the team load view."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from erf.core.errors import Forbidden, ValidationFailed
from erf.db.models import ResourceAllocation, User
from erf.domain.enums import Role
from erf.repositories.requests import AllocationRepository
from erf.repositories.users import TeamRepository, UserRepository
from erf.schemas.reports import EngineerLoad, LoadAssignment, LoadOut
from erf.schemas.requests import AllocationCandidate, CandidateAssignment
from erf.services.access import AccessPolicy
from erf.services.context import ServiceContext
from erf.services.presenters import user_ref
from erf.services.request_service import RequestService

MAX_LOAD_DAYS = 370


class ResourceService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.access = AccessPolicy(ctx.session)
        self.users = UserRepository(ctx.session)
        self.allocations = AllocationRepository(ctx.session)

    def candidates(
        self, user: User, request_id: int, start: date | None = None, end: date | None = None
    ) -> list[AllocationCandidate]:
        """Engineers of the request's team with their other bookings. ``start`` and ``end`` override the
        request's own period, which is how a proposed date change is checked."""
        request = RequestService(self.ctx).load_visible(user, request_id)
        if not self.access.can_plan_resources(user, request.team_id):
            raise Forbidden("Only the team leader or director can see allocation candidates.")
        first = start or request.planned_start
        last = end or request.planned_end
        if request.team_id is None or first is None or last is None or last < first:
            return []
        engineers = list(self.users.with_role(Role.ENGINEER, team_id=request.team_id))
        busy = self._group(
            self.allocations.active_in_period(
                [e.id for e in engineers], first, last, exclude_request_id=request.id
            )
        )
        preferred = set(request.preferred_engineer_ids)
        result = [
            AllocationCandidate(
                engineer=user_ref(e),
                skills=e.skills,
                is_preferred=e.id in preferred,
                overlapping=[
                    CandidateAssignment(
                        request_id=a.request_id,
                        display_no=a.request.display_no,
                        project_name=a.request.project_name,
                        start_date=a.start_date,
                        end_date=a.end_date,
                        allocation_pct=a.allocation_pct,
                        status=a.status,
                    )
                    for a in busy.get(e.id, [])
                ],
                peak_pct=peak_weekly_pct(busy.get(e.id, []), first, last),
            )
            for e in engineers
        ]
        result.sort(key=lambda c: (not c.is_preferred, c.peak_pct, c.engineer.display_name))
        return result

    def load(self, user: User, start: date, end: date, team_id: int | None) -> LoadOut:
        if end < start:
            raise ValidationFailed("The end date must be on or after the start date.")
        if (end - start).days > MAX_LOAD_DAYS:
            raise ValidationFailed("Choose a period of at most one year.")
        if user.has_role(Role.DIRECTOR, Role.ADMIN, Role.VIEWER):
            team_ids = [team_id] if team_id else None
        else:
            led = self.access.led_team_ids(user)
            if not led:
                raise Forbidden("Only team leaders and directors can view resource load.")
            if team_id and team_id not in led:
                raise Forbidden("You can only view the load of teams you lead.")
            team_ids = [team_id] if team_id else led
        engineers = [
            e for e in self.users.with_role(Role.ENGINEER) if team_ids is None or e.team_id in team_ids
        ]
        busy = self._group(self.allocations.active_in_period([e.id for e in engineers], start, end))
        teams = {t.id: t.name for t in TeamRepository(self.s).list_all()}
        return LoadOut(
            start=start,
            end=end,
            engineers=[
                EngineerLoad(
                    engineer=user_ref(e),
                    team_id=e.team_id,
                    team_name=teams.get(e.team_id) if e.team_id else None,
                    skills=e.skills,
                    assignments=[
                        LoadAssignment(
                            request_id=a.request_id,
                            display_no=a.request.display_no,
                            project_name=a.request.project_name,
                            client_name=a.request.client_name,
                            start_date=a.start_date,
                            end_date=a.end_date,
                            allocation_pct=a.allocation_pct,
                            status=a.status,
                        )
                        for a in busy.get(e.id, [])
                    ],
                )
                for e in sorted(engineers, key=lambda u: (teams.get(u.team_id or 0, ""), u.display_name))
            ],
        )

    @staticmethod
    def _group(rows: object) -> dict[int, list[ResourceAllocation]]:
        grouped: dict[int, list[ResourceAllocation]] = defaultdict(list)
        for a in rows:  # type: ignore[attr-defined]
            grouped[a.engineer_id].append(a)
        return grouped


def peak_weekly_pct(allocations: list[ResourceAllocation], first: date, last: date) -> int:
    """The highest total booking in any working week of [first, last]. Summing every overlapping
    allocation would overstate the load when those allocations do not overlap each other."""
    if not allocations:
        return 0
    peak = 0
    week = first - timedelta(days=first.weekday())
    while week <= last:
        friday = week + timedelta(days=4)
        total = sum(a.allocation_pct for a in allocations if a.start_date <= friday and a.end_date >= week)
        peak = max(peak, total)
        week += timedelta(weeks=1)
    return peak
