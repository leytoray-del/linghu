from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from erf.db.base import Base, TimestampMixin
from erf.domain.enums import Role

if TYPE_CHECKING:
    from erf.db.models.team import Team


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(120))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    skills: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    team: Mapped[Team | None] = relationship(lazy="joined")
    role_rows: Mapped[list[UserRole]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", back_populates="user"
    )

    @property
    def roles(self) -> set[Role]:
        return {Role(r.role) for r in self.role_rows}

    def has_role(self, *roles: Role) -> bool:
        return bool(self.roles & set(roles))

    def set_roles(self, roles: set[Role]) -> None:
        current = {r.role: r for r in self.role_rows}
        for code in list(current):
            if Role(code) not in roles:
                self.role_rows.remove(current[code])
        for role in roles:
            if role.value not in current:
                self.role_rows.append(UserRole(role=role.value))


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)

    user: Mapped[User] = relationship(back_populates="role_rows")


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(lazy="joined")
