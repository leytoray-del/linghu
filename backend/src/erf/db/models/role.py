"""Roles and the permissions they grant, maintained by administrators."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from erf.db.base import Base, TimestampMixin, utcnow


class RoleRow(TimestampMixin, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """System roles come with the software and cannot be deleted; custom roles are added by administrators."""

    grants: Mapped[list[RolePermission]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", back_populates="role"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code", ondelete="CASCADE"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)

    role: Mapped[RoleRow] = relationship(back_populates="grants")


class KnownPermission(Base):
    """Permissions whose default grants have been applied once. A permission added in a later version gets
    its defaults on the next start; grants an administrator changed afterwards are never overwritten."""

    __tablename__ = "known_permissions"

    permission: Mapped[str] = mapped_column(String(64), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
