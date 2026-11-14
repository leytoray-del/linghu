from __future__ import annotations

from pydantic import Field

from erf.schemas.common import Schema


class PermissionOut(Schema):
    key: str
    module: str
    module_name: str
    label: str
    description: str


class RoleOut(Schema):
    code: str
    name: str
    description: str | None
    is_system: bool
    is_locked: bool
    is_base: bool
    duty: str | None
    permissions: list[str]
    user_count: int


class RoleIn(Schema):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list, max_length=100)


class RolesOut(Schema):
    roles: list[RoleOut]
    permissions: list[PermissionOut]
