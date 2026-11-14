"""Request-scoped dependencies: unit of work, signed-in user, CSRF protection and role checks."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request

from erf.api.container import Container
from erf.core.errors import Forbidden, Unauthorized
from erf.db.models import User
from erf.db.session import session_scope
from erf.domain.enums import Role
from erf.domain.permissions import Permission
from erf.services.auth_service import AuthService
from erf.services.context import ServiceContext
from erf.services.permission_service import can

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def _unit_of_work(container: Annotated[Container, Depends(get_container)]) -> Iterator[ServiceContext]:
    with session_scope(container.factory) as session:
        yield ServiceContext(session, container.clock, container.settings)


# The transaction commits after the endpoint returns and before the response is sent,
# so a client never sees success for a change that failed to commit.
Ctx = Annotated[ServiceContext, Depends(_unit_of_work, scope="function")]


def current_user(request: Request, ctx: Ctx) -> User:
    token = request.cookies.get(ctx.settings.session_cookie_name)
    user = AuthService(ctx).resolve(token)
    if user is None:
        raise Unauthorized("Your session has ended. Sign in again.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        expected = request.cookies.get(ctx.settings.csrf_cookie_name, "")
        if not expected or not secrets.compare_digest(sent, expected):
            raise Forbidden(
                "The request could not be verified. Refresh the page and try again.", code="csrf_failed"
            )
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    def checker(user: CurrentUser) -> User:
        if not user.has_role(*roles):
            raise Forbidden("You do not have permission for this page.")
        return user

    return checker


def require_permission(permission: Permission) -> Callable[..., User]:
    def checker(user: CurrentUser, ctx: Ctx) -> User:
        if not can(ctx.session, user, permission):
            raise Forbidden("You do not have permission for this page.")
        return user

    return checker
