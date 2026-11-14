"""What a user may do: the permissions granted by their roles, read from the database."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from erf.db.models import RolePermission, User
from erf.domain.permissions import LOCKED_ROLE, Permission

_CACHE_KEY = "erf.permissions"


def permissions_of(session: Session, user: User) -> set[Permission]:
    """The union of the permissions of the user's roles. Cached for the unit of work."""
    cache: dict[int, set[Permission]] = session.info.setdefault(_CACHE_KEY, {})
    if user.id in cache:
        return cache[user.id]
    roles = user.roles
    if LOCKED_ROLE.value in roles:
        granted = set(Permission)
    else:
        known = {p.value for p in Permission}
        rows = session.scalars(select(RolePermission.permission).where(RolePermission.role_code.in_(roles)))
        granted = {Permission(p) for p in rows if p in known}
    cache[user.id] = granted
    return granted


def can(session: Session, user: User, permission: Permission) -> bool:
    return permission in permissions_of(session, user)


def forget(session: Session) -> None:
    """Drop cached permissions after roles or grants change."""
    session.info.pop(_CACHE_KEY, None)
