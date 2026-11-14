from __future__ import annotations

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from erf.api.deps import Ctx, require_permission
from erf.core.errors import ValidationFailed
from erf.db.models import User
from erf.domain.enums import OutboxStatus
from erf.domain.permissions import Permission
from erf.repositories.settings import SupportTypeRepository
from erf.repositories.users import TeamRepository, UserRepository
from erf.schemas.admin import (
    EmailTestIn,
    EmailTestOut,
    HolidayAdminOut,
    HolidayIn,
    OutboxSummary,
    SettingIn,
    SettingOut,
    SupportTypeIn,
    SupportTypeOut,
    TeamApproversIn,
    TeamOut,
    TemporaryPasswordOut,
    UserCreateIn,
    UserImportIn,
    UserImportOut,
    UserOut,
    UserUpdateIn,
)
from erf.schemas.auth import TeamBrief
from erf.schemas.roles import RoleIn, RoleOut, RolesOut
from erf.services.admin_service import AdminService
from erf.services.role_service import RoleService
from erf.services.user_import_service import UserImportService

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Annotated[User, Depends(require_permission(Permission.CORE_ADMIN))]


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        job_title=u.job_title,
        team=TeamBrief.model_validate(u.team) if u.team else None,
        skills=u.skills,
        roles=sorted(u.roles),
        is_active=u.is_active,
        must_change_password=u.must_change_password,
        last_login_at=u.last_login_at,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(admin: Admin, ctx: Ctx) -> list[UserOut]:
    return [user_out(u) for u in UserRepository(ctx.session).list_all()]


@router.post("/users", response_model=TemporaryPasswordOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreateIn, admin: Admin, ctx: Ctx) -> TemporaryPasswordOut:
    user, password = AdminService(ctx, admin).create_user(body)
    ctx.session.flush()
    return TemporaryPasswordOut(user=user_out(user), temporary_password=password)


@router.get("/users/import-template.xlsx", response_class=Response)
def user_import_template(admin: Admin, ctx: Ctx) -> Response:
    return Response(
        UserImportService(ctx).template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="user-import-template.xlsx"'},
    )


@router.post("/users/import", response_model=UserImportOut)
def import_users(body: UserImportIn, admin: Admin, ctx: Ctx) -> UserImportOut:
    try:
        content = base64.b64decode(body.file_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationFailed("This file could not be read. Choose the Excel file again.") from None
    return UserImportService(ctx).run(content, body.initial_password, apply=body.apply)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdateIn, admin: Admin, ctx: Ctx) -> UserOut:
    return user_out(AdminService(ctx, admin).update_user(user_id, body))


@router.post("/users/{user_id}/reset-password", response_model=TemporaryPasswordOut)
def reset_password(user_id: int, admin: Admin, ctx: Ctx) -> TemporaryPasswordOut:
    user, password = AdminService(ctx, admin).reset_password(user_id)
    return TemporaryPasswordOut(user=user_out(user), temporary_password=password)


@router.get("/teams", response_model=list[TeamOut])
def list_teams(admin: Admin, ctx: Ctx) -> list[TeamOut]:
    service = AdminService(ctx, admin)
    return [service.team_out(t.id) for t in TeamRepository(ctx.session).list_all()]


@router.put("/teams/{team_id}/approvers", response_model=TeamOut)
def set_approvers(team_id: int, body: TeamApproversIn, admin: Admin, ctx: Ctx) -> TeamOut:
    return AdminService(ctx, admin).set_team_approvers(team_id, body.approver_ids)


@router.get("/support-types", response_model=list[SupportTypeOut])
def list_support_types(admin: Admin, ctx: Ctx) -> list[SupportTypeOut]:
    return [SupportTypeOut.model_validate(s) for s in SupportTypeRepository(ctx.session).list_all()]


@router.post("/support-types", response_model=SupportTypeOut, status_code=status.HTTP_201_CREATED)
def create_support_type(body: SupportTypeIn, admin: Admin, ctx: Ctx) -> SupportTypeOut:
    return SupportTypeOut.model_validate(AdminService(ctx, admin).save_support_type(body))


@router.put("/support-types/{type_id}", response_model=SupportTypeOut)
def update_support_type(type_id: int, body: SupportTypeIn, admin: Admin, ctx: Ctx) -> SupportTypeOut:
    return SupportTypeOut.model_validate(AdminService(ctx, admin).save_support_type(body, type_id))


@router.get("/holidays", response_model=list[HolidayAdminOut])
def list_holidays(admin: Admin, ctx: Ctx, year: int | None = None) -> list[HolidayAdminOut]:
    return [HolidayAdminOut.model_validate(h) for h in AdminService(ctx, admin).holidays(year)]


@router.post("/holidays", response_model=HolidayAdminOut, status_code=status.HTTP_201_CREATED)
def add_holiday(body: HolidayIn, admin: Admin, ctx: Ctx) -> HolidayAdminOut:
    return HolidayAdminOut.model_validate(AdminService(ctx, admin).add_holiday(body))


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(holiday_id: int, admin: Admin, ctx: Ctx) -> Response:
    AdminService(ctx, admin).delete_holiday(holiday_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings", response_model=list[SettingOut])
def list_settings(admin: Admin, ctx: Ctx) -> list[SettingOut]:
    return AdminService(ctx, admin).settings()


@router.put("/settings/{key}", response_model=list[SettingOut])
def update_setting(key: str, body: SettingIn, admin: Admin, ctx: Ctx) -> list[SettingOut]:
    return AdminService(ctx, admin).set_setting(key, body.value)


@router.get("/outbox", response_model=OutboxSummary)
def outbox(admin: Admin, ctx: Ctx, status_filter: OutboxStatus | None = None) -> OutboxSummary:
    return AdminService(ctx, admin).outbox(status_filter)


@router.post("/email-test", response_model=EmailTestOut)
def send_test_email(body: EmailTestIn, admin: Admin, ctx: Ctx) -> EmailTestOut:
    return AdminService(ctx, admin).send_test_email(str(body.to))


@router.post("/outbox/{row_id}/retry", status_code=status.HTTP_204_NO_CONTENT)
def retry_outbox(row_id: int, admin: Admin, ctx: Ctx) -> Response:
    AdminService(ctx, admin).retry_email(row_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- roles and permissions ----


@router.get("/roles", response_model=RolesOut)
def roles(admin: Admin, ctx: Ctx) -> RolesOut:
    service = RoleService(ctx.session)
    return RolesOut(roles=service.list_roles(), permissions=service.catalogue())


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleIn, admin: Admin, ctx: Ctx) -> RoleOut:
    return RoleService(ctx.session).create(body)


@router.put("/roles/{code}", response_model=RoleOut)
def update_role(code: str, body: RoleIn, admin: Admin, ctx: Ctx) -> RoleOut:
    return RoleService(ctx.session).update(code, body)


@router.delete("/roles/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(code: str, admin: Admin, ctx: Ctx) -> Response:
    RoleService(ctx.session).delete(code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
