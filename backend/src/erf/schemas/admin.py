from __future__ import annotations

from datetime import date, datetime

from pydantic import EmailStr, Field

from erf.domain.enums import Role
from erf.schemas.auth import TeamBrief
from erf.schemas.common import Schema, UserRef


class UserOut(Schema):
    id: int
    email: str
    display_name: str
    job_title: str | None
    team: TeamBrief | None
    skills: str | None
    roles: list[Role]
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None


class UserCreateIn(Schema):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    team_id: int | None = None
    skills: str | None = Field(default=None, max_length=200)
    roles: list[Role] = Field(default_factory=lambda: [Role.REQUESTER])


class UserUpdateIn(Schema):
    display_name: str = Field(min_length=1, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    team_id: int | None = None
    skills: str | None = Field(default=None, max_length=200)
    roles: list[Role]
    is_active: bool


class TemporaryPasswordOut(Schema):
    user: UserOut
    temporary_password: str


class TeamOut(Schema):
    id: int
    code: str
    name: str
    is_active: bool
    approvers: list[UserRef]


class TeamApproversIn(Schema):
    approver_ids: list[int] = Field(max_length=10)


class SupportTypeOut(Schema):
    id: int
    code: str
    name: str
    team_id: int
    sort_order: int
    is_active: bool


class SupportTypeIn(Schema):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    team_id: int
    sort_order: int = 0
    is_active: bool = True


class HolidayAdminOut(Schema):
    id: int
    holiday_date: date
    name: str


class HolidayIn(Schema):
    holiday_date: date
    name: str = Field(min_length=1, max_length=120)


class SettingOut(Schema):
    key: str
    value: str
    description: str


class SettingIn(Schema):
    value: str = Field(min_length=1, max_length=64)


class OutboxOut(Schema):
    id: int
    event_type: str
    request_id: int | None
    to_addresses: list[str]
    cc_addresses: list[str]
    subject: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class OutboxSummary(Schema):
    counts: dict[str, int]
    items: list[OutboxOut]
    backend: str
