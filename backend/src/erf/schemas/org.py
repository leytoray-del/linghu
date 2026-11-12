from __future__ import annotations

from pydantic import Field

from erf.domain.enums import LocationKind
from erf.schemas.common import Schema, UserRef


class ProjectOut(Schema):
    id: int
    code: str
    name: str
    client_name: str | None
    pm: UserRef | None
    remarks: str | None
    is_active: bool


class ProjectIn(Schema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    client_name: str | None = Field(default=None, max_length=200)
    pm_user_id: int | None = None
    remarks: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class LocationOut(Schema):
    id: int
    name: str
    kind: LocationKind
    is_active: bool


class LocationIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    kind: LocationKind
    is_active: bool = True
