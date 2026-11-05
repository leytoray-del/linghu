from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from erf.db.models import Team, User, UserRole, UserSession
from erf.domain.enums import Role


class UserRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, user_id: int) -> User | None:
        return self.s.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.s.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))

    def list_all(self, *, include_inactive: bool = True) -> Sequence[User]:
        stmt = select(User).order_by(User.display_name)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        return self.s.scalars(stmt).unique().all()

    def with_role(self, role: Role, *, team_id: int | None = None) -> Sequence[User]:
        stmt = (
            select(User)
            .join(UserRole)
            .where(UserRole.role == role.value, User.is_active.is_(True))
            .order_by(User.display_name)
        )
        if team_id is not None:
            stmt = stmt.where(User.team_id == team_id)
        return self.s.scalars(stmt).unique().all()

    def get_many(self, ids: list[int]) -> Sequence[User]:
        if not ids:
            return []
        return self.s.scalars(select(User).where(User.id.in_(ids))).unique().all()

    def add(self, user: User) -> User:
        self.s.add(user)
        self.s.flush()
        return user


class TeamRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, team_id: int) -> Team | None:
        return self.s.get(Team, team_id)

    def list_all(self) -> Sequence[Team]:
        return self.s.scalars(select(Team).order_by(Team.name)).unique().all()

    def teams_led_by(self, user_id: int) -> list[int]:
        from erf.db.models import TeamApprover

        return list(self.s.scalars(select(TeamApprover.team_id).where(TeamApprover.user_id == user_id)))


class SessionRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, token_hash: str) -> UserSession | None:
        return self.s.get(UserSession, token_hash)

    def add(self, row: UserSession) -> None:
        self.s.add(row)

    def delete(self, token_hash: str) -> None:
        self.s.execute(delete(UserSession).where(UserSession.token_hash == token_hash))

    def delete_for_user(self, user_id: int, *, except_hash: str | None = None) -> None:
        stmt = delete(UserSession).where(UserSession.user_id == user_id)
        if except_hash:
            stmt = stmt.where(UserSession.token_hash != except_hash)
        self.s.execute(stmt)

    def purge_expired(self, now: datetime) -> int:
        result = self.s.execute(delete(UserSession).where(UserSession.expires_at < now))
        return int(getattr(result, "rowcount", 0) or 0)
