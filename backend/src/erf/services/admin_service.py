"""Administration of users, teams, support types, holidays, workflow settings and the email queue."""

from __future__ import annotations

import json
import secrets
import string

from sqlalchemy.exc import IntegrityError

from erf.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from erf.core.security import hash_password
from erf.db.models import Holiday, SupportType, TeamApprover, User
from erf.domain.enums import OutboxStatus, Role
from erf.repositories.requests import OutboxRepository
from erf.repositories.settings import SETTING_DEFAULTS, HolidayRepository, SupportTypeRepository
from erf.repositories.users import SessionRepository, TeamRepository, UserRepository
from erf.schemas.admin import (
    HolidayIn,
    OutboxOut,
    OutboxSummary,
    SettingOut,
    SupportTypeIn,
    TeamOut,
    UserCreateIn,
    UserUpdateIn,
)
from erf.services.context import ServiceContext
from erf.services.presenters import user_ref

INT_SETTINGS = {k for k in SETTING_DEFAULTS if k != "request_no_prefix"}


def temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12)) + "!7"


class AdminService:
    def __init__(self, ctx: ServiceContext, actor: User):
        if not actor.has_role(Role.ADMIN):
            raise Forbidden("Only administrators can change system settings.")
        self.ctx = ctx
        self.s = ctx.session
        self.actor = actor
        self.users = UserRepository(ctx.session)
        self.teams = TeamRepository(ctx.session)

    # ---------------------------------------------------------------- users

    def _user(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise NotFound("This user does not exist.")
        return user

    def _check_team(self, team_id: int | None) -> None:
        if team_id is not None and self.teams.get(team_id) is None:
            raise ValidationFailed("Choose a valid team.", details={"fields": {"team_id": "Unknown team."}})

    def create_user(self, data: UserCreateIn) -> tuple[User, str]:
        if self.users.get_by_email(data.email):
            raise Conflict(
                "A user with this email already exists.", details={"fields": {"email": "Already used."}}
            )
        self._check_team(data.team_id)
        password = temporary_password()
        user = User(
            email=str(data.email).lower(),
            display_name=data.display_name.strip(),
            job_title=data.job_title,
            team_id=data.team_id,
            skills=data.skills,
            password_hash=hash_password(password),
            must_change_password=True,
            is_active=True,
        )
        user.set_roles(set(data.roles) | {Role.REQUESTER})
        self.users.add(user)
        return user, password

    def update_user(self, user_id: int, data: UserUpdateIn) -> User:
        user = self._user(user_id)
        self._check_team(data.team_id)
        roles = set(data.roles)
        if user.id == self.actor.id and (Role.ADMIN not in roles or not data.is_active):
            raise ValidationFailed("You cannot remove your own administrator access or deactivate yourself.")
        user.display_name = data.display_name.strip()
        user.job_title = data.job_title
        user.team_id = data.team_id
        user.skills = data.skills
        user.set_roles(roles)
        if user.is_active and not data.is_active:
            SessionRepository(self.s).delete_for_user(user.id)
        user.is_active = data.is_active
        self.s.flush()
        return user

    def reset_password(self, user_id: int) -> tuple[User, str]:
        user = self._user(user_id)
        password = temporary_password()
        user.password_hash = hash_password(password)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_until = None
        SessionRepository(self.s).delete_for_user(user.id)
        return user, password

    # ---------------------------------------------------------------- teams

    def team_out(self, team_id: int) -> TeamOut:
        team = self.teams.get(team_id)
        if team is None:
            raise NotFound("This team does not exist.")
        approvers = self.users.get_many(team.approver_ids)
        return TeamOut(
            id=team.id,
            code=team.code,
            name=team.name,
            is_active=team.is_active,
            approvers=[user_ref(u) for u in approvers],
        )

    def set_team_approvers(self, team_id: int, approver_ids: list[int]) -> TeamOut:
        team = self.teams.get(team_id)
        if team is None:
            raise NotFound("This team does not exist.")
        ids = list(dict.fromkeys(approver_ids))
        if not ids:
            raise ValidationFailed("A team needs at least one approver.")
        users = self.users.get_many(ids)
        if len(users) != len(ids) or any(not u.is_active or not u.has_role(Role.TEAM_LEADER) for u in users):
            raise ValidationFailed("Approvers must be active users with the team leader role.")
        team.approver_rows = [TeamApprover(user_id=i) for i in ids]
        self.s.flush()
        return self.team_out(team_id)

    # ---------------------------------------------------------------- support types

    def save_support_type(self, data: SupportTypeIn, type_id: int | None = None) -> SupportType:
        self._check_team(data.team_id)
        repo = SupportTypeRepository(self.s)
        row = repo.get(type_id) if type_id else SupportType()
        if row is None:
            raise NotFound("This type of support does not exist.")
        row.code = data.code
        row.name = data.name.strip()
        row.team_id = data.team_id
        row.sort_order = data.sort_order
        row.is_active = data.is_active
        if type_id is None:
            self.s.add(row)
        try:
            self.s.flush()
        except IntegrityError as exc:
            raise Conflict("Another type of support already uses this code.") from exc
        return row

    # ---------------------------------------------------------------- holidays

    def add_holiday(self, data: HolidayIn) -> Holiday:
        row = Holiday(holiday_date=data.holiday_date, name=data.name.strip())
        self.s.add(row)
        try:
            self.s.flush()
        except IntegrityError as exc:
            raise Conflict("A holiday already exists on this date.") from exc
        return row

    def delete_holiday(self, holiday_id: int) -> None:
        row = self.s.get(Holiday, holiday_id)
        if row is None:
            raise NotFound("This holiday does not exist.")
        self.s.delete(row)

    def holidays(self, year: int | None) -> list[Holiday]:
        return list(HolidayRepository(self.s).list_year(year))

    # ---------------------------------------------------------------- settings

    def settings(self) -> list[SettingOut]:
        return [SettingOut(key=k, value=v, description=d) for k, (v, d) in self.ctx.config.all().items()]

    def set_setting(self, key: str, value: str) -> list[SettingOut]:
        if key not in SETTING_DEFAULTS:
            raise NotFound("Unknown setting.")
        value = value.strip()
        if key in INT_SETTINGS:
            if not value.isdigit() or not 0 < int(value) <= 1000:
                raise ValidationFailed("Enter a whole number between 1 and 1000.")
        elif not value.replace("-", "").isalnum():
            raise ValidationFailed("Use letters, digits and hyphens only.")
        self.ctx.config.set(key, value)
        return self.settings()

    # ---------------------------------------------------------------- email queue

    def outbox(self, status: OutboxStatus | None) -> OutboxSummary:
        repo = OutboxRepository(self.s)
        return OutboxSummary(
            counts=repo.counts(),
            backend=self.ctx.settings.mail_backend,
            items=[
                OutboxOut(
                    id=o.id,
                    event_type=o.event_type,
                    request_id=o.request_id,
                    to_addresses=json.loads(o.to_addresses),
                    cc_addresses=json.loads(o.cc_addresses),
                    subject=o.subject,
                    status=o.status,
                    attempts=o.attempts,
                    last_error=o.last_error,
                    created_at=o.created_at,
                    sent_at=o.sent_at,
                )
                for o in repo.recent(200, status)
            ],
        )

    def retry_email(self, row_id: int) -> None:
        row = OutboxRepository(self.s).get(row_id)
        if row is None:
            raise NotFound("This email does not exist.")
        if row.status != OutboxStatus.FAILED.value:
            raise ValidationFailed("Only failed emails can be retried.")
        row.status = OutboxStatus.PENDING.value
        row.attempts = 0
        row.next_attempt_at = self.ctx.clock.now()
