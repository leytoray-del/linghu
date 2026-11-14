"""Roles: listing, adding, changing and deleting them, and applying default grants."""

from __future__ import annotations

import re

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from erf.core.errors import Conflict, NotFound, ValidationFailed
from erf.db.models import KnownPermission, RolePermission, RoleRow, User, UserRole
from erf.domain.enums import Role
from erf.domain.permissions import BASE_ROLE, CATALOGUE, LOCKED_ROLE, MODULES, SYSTEM_ROLES, Permission
from erf.schemas.roles import PermissionOut, RoleIn, RoleOut
from erf.services.permission_service import forget


def ensure_roles(session: Session) -> None:
    """Create missing system roles, grant each new permission to its default roles once, and give every user
    the base role. Safe to run at every start; it never undoes an administrator's change."""
    existing = {r.code: r for r in session.scalars(select(RoleRow))}
    for role, spec in SYSTEM_ROLES.items():
        if role.value not in existing:
            row = RoleRow(code=role.value, name=spec.name, description=spec.description, is_system=True)
            session.add(row)
            existing[role.value] = row
    session.flush()
    known = set(session.scalars(select(KnownPermission.permission)))
    for permission in Permission:
        if permission.value in known:
            continue
        for role, spec in SYSTEM_ROLES.items():
            if role != LOCKED_ROLE and permission in spec.defaults:
                session.merge(RolePermission(role_code=role.value, permission=permission.value))
        session.add(KnownPermission(permission=permission.value))
    session.flush()
    users_without_base = session.scalars(
        select(User).where(~User.role_rows.any(UserRole.role == BASE_ROLE.value))
    )
    for u in users_without_base:
        u.role_rows.append(UserRole(role=BASE_ROLE.value))
    session.flush()


def _slug(name: str) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:28] or "ROLE"
    return code if code[0].isalpha() else f"R_{code}"[:28]


class RoleService:
    def __init__(self, session: Session):
        self.s = session

    def catalogue(self) -> list[PermissionOut]:
        return [
            PermissionOut(
                key=p.value,
                module=info.module,
                module_name=MODULES[info.module],
                label=info.label,
                description=info.description,
            )
            for p, info in CATALOGUE.items()
        ]

    def _out(self, row: RoleRow, counts: dict[str, int]) -> RoleOut:
        system = SYSTEM_ROLES.get(Role(row.code)) if row.code in Role._value2member_map_ else None
        locked = row.code == LOCKED_ROLE.value
        return RoleOut(
            code=row.code,
            name=row.name,
            description=row.description,
            is_system=row.is_system,
            is_locked=locked,
            is_base=row.code == BASE_ROLE.value,
            duty=system.duty if system else None,
            permissions=sorted(p.value for p in Permission)
            if locked
            else sorted(g.permission for g in row.grants),
            user_count=counts.get(row.code, 0),
        )

    def _counts(self) -> dict[str, int]:
        rows = self.s.execute(
            select(UserRole.role, func.count())
            .join(User, User.id == UserRole.user_id)
            .where(User.is_active.is_(True))
            .group_by(UserRole.role)
        ).tuples()
        return {code: n for code, n in rows}

    def list_roles(self) -> list[RoleOut]:
        order = {r.value: i for i, r in enumerate(SYSTEM_ROLES)}
        rows = sorted(self.s.scalars(select(RoleRow)), key=lambda r: (order.get(r.code, 100), r.name.lower()))
        counts = self._counts()
        return [self._out(r, counts) for r in rows]

    def codes(self) -> set[str]:
        return set(self.s.scalars(select(RoleRow.code)))

    def _get(self, code: str) -> RoleRow:
        row = self.s.get(RoleRow, code)
        if row is None:
            raise NotFound("This role does not exist.")
        return row

    def _check(self, data: RoleIn, code: str | None) -> list[str]:
        known = {p.value for p in Permission}
        unknown = [p for p in data.permissions if p not in known]
        if unknown:
            raise ValidationFailed("Some permissions do not exist: " + ", ".join(unknown) + ".")
        name = data.name.strip()
        clash = self.s.scalar(select(RoleRow).where(func.lower(RoleRow.name) == name.lower()))
        if clash is not None and clash.code != code:
            raise Conflict(
                "Another role already has this name.", details={"fields": {"name": "Already used."}}
            )
        return sorted(set(data.permissions))

    def create(self, data: RoleIn) -> RoleOut:
        permissions = self._check(data, None)
        code = base = _slug(data.name)
        n = 2
        while self.s.get(RoleRow, code) is not None:
            code = f"{base[:25]}_{n}"
            n += 1
        row = RoleRow(
            code=code,
            name=data.name.strip(),
            description=(data.description or "").strip() or None,
            is_system=False,
        )
        row.grants = [RolePermission(permission=p) for p in permissions]
        self.s.add(row)
        self.s.flush()
        forget(self.s)
        return self._out(row, {})

    def update(self, code: str, data: RoleIn) -> RoleOut:
        row = self._get(code)
        if code == LOCKED_ROLE.value:
            raise ValidationFailed(
                "The Administrator role always has every permission and cannot be changed."
            )
        permissions = self._check(data, code)
        if not row.is_system:
            row.name = data.name.strip()
        row.description = (data.description or "").strip() or None
        current = {g.permission: g for g in row.grants}
        for p in list(current):
            if p not in permissions:
                row.grants.remove(current[p])
        for p in permissions:
            if p not in current:
                row.grants.append(RolePermission(permission=p))
        self.s.flush()
        forget(self.s)
        return self._out(row, self._counts())

    def delete(self, code: str) -> None:
        row = self._get(code)
        if row.is_system:
            raise ValidationFailed("System roles cannot be deleted. Remove permissions from them instead.")
        users = self._counts().get(code, 0)
        if users:
            raise ValidationFailed(
                f"{users} active user{'s have' if users != 1 else ' has'} this role. Remove it from them first."
            )
        self.s.execute(delete(UserRole).where(UserRole.role == code))
        self.s.delete(row)
        self.s.flush()
        forget(self.s)
