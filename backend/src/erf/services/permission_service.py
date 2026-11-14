"""What a user may do: the permissions granted by their roles, read from the database."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from erf.db.models import RolePermission, User, UserRole
from erf.domain.permissions import ADMIN_PERMISSIONS, CATALOGUE, LOCKED_ROLE, Permission

_CACHE_KEY = "erf.permissions"


def permissions_of(session: Session, user: User) -> set[Permission]:
    """The union of the permissions of the user's roles. Cached for the unit of work."""
    cache: dict[int, set[Permission]] = session.info.setdefault(_CACHE_KEY, {})
    if user.id in cache:
        return cache[user.id]
    roles = user.roles
    known = {p.value for p in Permission}
    rows = session.scalars(select(RolePermission.permission).where(RolePermission.role_code.in_(roles)))
    granted = {Permission(p) for p in rows if p in known}
    if LOCKED_ROLE.value in roles:
        granted |= ADMIN_PERMISSIONS
    cache[user.id] = granted
    return granted


def can(session: Session, user: User, permission: Permission) -> bool:
    return permission in permissions_of(session, user)


def forget(session: Session) -> None:
    """Drop cached permissions after roles or grants change."""
    session.info.pop(_CACHE_KEY, None)


def users_with(session: Session, permission: Permission, *, team_id: int | None = None) -> list[User]:
    """Active users whose roles grant a permission, by name. Used to find approvers and assignable people."""
    codes = set(
        session.scalars(select(RolePermission.role_code).where(RolePermission.permission == permission.value))
    )
    if not CATALOGUE[permission].duty:
        codes.add(LOCKED_ROLE.value)
    if not codes:
        return []
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role.in_(codes), User.is_active.is_(True))
        .order_by(User.display_name)
    )
    if team_id is not None:
        stmt = stmt.where(User.team_id == team_id)
    return list(session.scalars(stmt).unique().all())
