"""Projects and locations, shared by every module."""

from __future__ import annotations

from sqlalchemy import func, select

from erf.core.errors import Conflict, NotFound, ValidationFailed
from erf.db.models import Location, Project, User
from erf.schemas.org import LocationIn, LocationOut, ProjectIn, ProjectOut
from erf.services.context import ServiceContext
from erf.services.presenters import user_ref


def project_out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        code=p.code,
        name=p.name,
        client_name=p.client_name,
        pm=user_ref(p.pm) if p.pm else None,
        remarks=p.remarks,
        is_active=p.is_active,
    )


def location_out(loc: Location) -> LocationOut:
    return LocationOut.model_validate(loc)


class OrgService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session

    # ---- projects ----

    def projects(self, *, active_only: bool = False) -> list[Project]:
        q = select(Project).order_by(Project.is_active.desc(), Project.name)
        if active_only:
            q = q.where(Project.is_active.is_(True))
        return list(self.s.scalars(q))

    def project(self, project_id: int) -> Project:
        p = self.s.get(Project, project_id)
        if p is None:
            raise NotFound("This project does not exist.")
        return p

    def save_project(self, data: ProjectIn, project_id: int | None = None) -> Project:
        code = data.code.strip().upper()
        clash = self.s.scalar(select(Project).where(func.upper(Project.code) == code))
        if clash is not None and clash.id != project_id:
            raise Conflict(
                f"The project {clash.name} already uses the code {clash.code}.",
                details={"fields": {"code": "This code is already used."}},
            )
        if data.pm_user_id is not None:
            pm = self.s.get(User, data.pm_user_id)
            if pm is None or not pm.is_active:
                raise ValidationFailed(
                    "Choose an active user as the project manager.",
                    details={"fields": {"pm_user_id": "Choose an active user."}},
                )
        p = self.project(project_id) if project_id else Project()
        p.code = code
        p.name = data.name.strip()
        p.client_name = (data.client_name or "").strip() or None
        p.pm_user_id = data.pm_user_id
        p.remarks = data.remarks
        p.is_active = data.is_active
        if project_id is None:
            self.s.add(p)
        self.s.flush()
        self.s.refresh(p)
        return p

    # ---- locations ----

    def locations(self, *, active_only: bool = False) -> list[Location]:
        q = select(Location).order_by(Location.kind, Location.name)
        if active_only:
            q = q.where(Location.is_active.is_(True))
        return list(self.s.scalars(q))

    def location(self, location_id: int) -> Location:
        loc = self.s.get(Location, location_id)
        if loc is None:
            raise NotFound("This location does not exist.")
        return loc

    def save_location(self, data: LocationIn, location_id: int | None = None) -> Location:
        name = data.name.strip()
        clash = self.s.scalar(select(Location).where(func.lower(Location.name) == name.lower()))
        if clash is not None and clash.id != location_id:
            raise Conflict(
                "Another location already has this name.", details={"fields": {"name": "Already used."}}
            )
        loc = self.location(location_id) if location_id else Location()
        loc.name = name
        loc.kind = data.kind.value
        loc.is_active = data.is_active
        if location_id is None:
            self.s.add(loc)
        self.s.flush()
        return loc
