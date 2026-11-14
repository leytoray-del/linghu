from __future__ import annotations

from pydantic import Field

from erf.schemas.common import Schema


class LoginIn(Schema):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(Schema):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class TeamBrief(Schema):
    id: int
    code: str
    name: str


class Me(Schema):
    id: int
    email: str
    display_name: str
    job_title: str | None
    team: TeamBrief | None
    roles: list[str]
    role_names: list[str]
    """Names of the person's roles, without the base role every user has."""
    led_team_ids: list[int]
    scopes: list[str]
    permissions: list[str]
    must_change_password: bool
    pending_task_count: int
    withdrawal_task_count: int
    """Withdrawal requests waiting for this person's approval (as project PM or operations manager)."""
