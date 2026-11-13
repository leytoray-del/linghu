from __future__ import annotations

from fastapi import APIRouter, Request, Response

from erf.api.deps import Ctx, CurrentUser
from erf.core.errors import Unauthorized
from erf.db.models import User
from erf.domain.permissions import permissions_for
from erf.modules.inventory.withdrawals import WithdrawalService
from erf.schemas.auth import ChangePasswordIn, LoginIn, Me, TeamBrief
from erf.schemas.common import Message
from erf.services.access import AccessPolicy
from erf.services.auth_service import AuthService
from erf.services.context import ServiceContext
from erf.services.request_service import RequestService

router = APIRouter(prefix="/auth", tags=["auth"])


def build_me(ctx: ServiceContext, user: User) -> Me:
    access = AccessPolicy(ctx.session)
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        job_title=user.job_title,
        team=TeamBrief.model_validate(user.team) if user.team else None,
        roles=sorted(user.roles),
        led_team_ids=access.led_team_ids(user),
        scopes=[s.value for s in access.allowed_scopes(user)],
        permissions=sorted(p.value for p in permissions_for(user.roles)),
        must_change_password=user.must_change_password,
        pending_task_count=RequestService(ctx).pending_task_count(user),
        withdrawal_task_count=WithdrawalService(ctx).pending_count(user),
    )


@router.post("/login", response_model=Me)
def login(body: LoginIn, request: Request, response: Response, ctx: Ctx) -> Me:
    try:
        issued = AuthService(ctx).login(
            body.email,
            body.password,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except Unauthorized:
        # Keep the failed-attempt counter and any lockout even though the request fails.
        ctx.session.commit()
        raise
    s = ctx.settings
    response.set_cookie(
        s.session_cookie_name,
        issued.token,
        max_age=issued.expires_in_seconds,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        s.csrf_cookie_name,
        issued.csrf_token,
        max_age=issued.expires_in_seconds,
        httponly=False,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return build_me(ctx, issued.user)


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, ctx: Ctx) -> Message:
    s = ctx.settings
    AuthService(ctx).logout(request.cookies.get(s.session_cookie_name))
    response.delete_cookie(s.session_cookie_name, path="/")
    response.delete_cookie(s.csrf_cookie_name, path="/")
    return Message(message="Signed out.")


@router.get("/me", response_model=Me)
def me(user: CurrentUser, ctx: Ctx) -> Me:
    return build_me(ctx, user)


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, ctx: Ctx) -> Message:
    AuthService(ctx).change_password(
        user,
        body.current_password,
        body.new_password,
        keep_token=request.cookies.get(ctx.settings.session_cookie_name),
    )
    return Message(message="Password changed.")
