from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from erf.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from erf.db.models.user import User


class Team(TimestampMixin, Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    approver_rows: Mapped[list[TeamApprover]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", back_populates="team"
    )

    @property
    def approver_ids(self) -> list[int]:
        return [a.user_id for a in self.approver_rows]


class TeamApprover(Base):
    """Users who review requests routed to the team. Any one of them may act."""

    __tablename__ = "team_approvers"

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    team: Mapped[Team] = relationship(back_populates="approver_rows")
    user: Mapped[User] = relationship(lazy="joined")


class SupportType(TimestampMixin, Base):
    """A value of the "Type of support" field. Each type routes to one team."""

    __tablename__ = "support_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    team: Mapped[Team] = relationship(lazy="joined")
