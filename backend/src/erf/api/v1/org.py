"""Projects and locations, shared by every module. Reading is open to signed-in users; changes need core.admin."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from erf.api.deps import Ctx, CurrentUser, require_permission
from erf.db.models import User
from erf.domain.permissions import Permission
from erf.schemas.org import LocationIn, LocationOut, ProjectIn, ProjectOut
from erf.services.org_service import OrgService, location_out, project_out

router = APIRouter(tags=["organisation"])
CoreAdmin = Annotated[User, Depends(require_permission(Permission.CORE_ADMIN))]


@router.get("/projects", response_model=list[ProjectOut])
def projects(user: CurrentUser, ctx: Ctx) -> list[ProjectOut]:
    return [project_out(p) for p in OrgService(ctx).projects()]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, user: CoreAdmin, ctx: Ctx) -> ProjectOut:
    return project_out(OrgService(ctx).save_project(body))


@router.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectIn, user: CoreAdmin, ctx: Ctx) -> ProjectOut:
    return project_out(OrgService(ctx).save_project(body, project_id))


@router.get("/locations", response_model=list[LocationOut])
def locations(user: CurrentUser, ctx: Ctx) -> list[LocationOut]:
    return [location_out(loc) for loc in OrgService(ctx).locations()]


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(body: LocationIn, user: CoreAdmin, ctx: Ctx) -> LocationOut:
    return location_out(OrgService(ctx).save_location(body))


@router.put("/locations/{location_id}", response_model=LocationOut)
def update_location(location_id: int, body: LocationIn, user: CoreAdmin, ctx: Ctx) -> LocationOut:
    return location_out(OrgService(ctx).save_location(body, location_id))
