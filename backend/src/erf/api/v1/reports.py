from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from erf.api.deps import Ctx, CurrentUser
from erf.repositories.settings import SupportTypeRepository
from erf.repositories.users import TeamRepository
from erf.schemas.reports import DashboardOut, LoadOut, Lookups, ReportSummary
from erf.schemas.requests import SupportTypeBrief
from erf.services.report_service import ReportService
from erf.services.resource_service import ResourceService

router = APIRouter(tags=["reports"])


@router.get("/lookups", response_model=Lookups)
def lookups(user: CurrentUser, ctx: Ctx) -> Lookups:
    """Reference data the request form needs: support types, teams with engineers, and the notice rule."""
    from erf.domain.permissions import Permission
    from erf.repositories.users import UserRepository
    from erf.services.permission_service import users_with

    users = UserRepository(ctx.session)
    engineers = users_with(ctx.session, Permission.RESOURCES_ASSIGNABLE)
    teams = [
        {
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "engineers": [
                {"id": e.id, "display_name": e.display_name, "skills": e.skills}
                for e in engineers
                if e.team_id == t.id
            ],
            "approvers": [u.display_name for u in users.get_many(t.approver_ids) if u.is_active],
        }
        for t in TeamRepository(ctx.session).list_all()
        if t.is_active
    ]
    return Lookups(
        support_types=[
            SupportTypeBrief.model_validate(s)
            for s in SupportTypeRepository(ctx.session).list_all(active_only=True)
        ],
        teams=teams,
        directors=[u.display_name for u in users_with(ctx.session, Permission.RESOURCES_APPROVE)],
        min_notice_working_days=ctx.config.get_int("min_notice_working_days"),
        today=ctx.clock.today(),
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser, ctx: Ctx) -> DashboardOut:
    return ReportService(ctx).dashboard(user)


@router.get("/reports/summary", response_model=ReportSummary)
def report_summary(
    user: CurrentUser, ctx: Ctx, year: Annotated[int | None, Query(ge=2020, le=2100)] = None
) -> ReportSummary:
    return ReportService(ctx).summary(user, year or ctx.clock.today().year)


@router.get("/resources/load", response_model=LoadOut)
def resource_load(
    user: CurrentUser,
    ctx: Ctx,
    start: date | None = None,
    end: date | None = None,
    team_id: int | None = None,
) -> LoadOut:
    today = ctx.clock.today()
    first = start or today - timedelta(days=today.weekday())
    last = end or first + timedelta(weeks=12) - timedelta(days=1)
    return ResourceService(ctx).load(user, first, last, team_id)
