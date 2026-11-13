"""Inventory tables. Every table carries the ``inv_`` prefix."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from erf.db.base import Base, TimestampMixin, utcnow
from erf.db.models.org import Location, Project
from erf.db.models.user import User


class InvCategory(TimestampMixin, Base):
    __tablename__ = "inv_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    tracking: Mapped[str] = mapped_column(String(16), nullable=False, default="SERIAL")
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    warranty_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InvModel(TimestampMixin, Base):
    __tablename__ = "inv_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("inv_categories.id"), nullable=False)
    model_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    serial_pattern: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category: Mapped[InvCategory] = relationship(lazy="joined")


class InvSupplier(TimestampMixin, Base):
    __tablename__ = "inv_suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InvDelivery(TimestampMixin, Base):
    __tablename__ = "inv_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("inv_suppliers.id"))
    delivery_order_no: Mapped[str | None] = mapped_column(String(64))
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    received_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remarks: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(lazy="joined")
    supplier: Mapped[InvSupplier | None] = relationship(lazy="joined")
    received_by: Mapped[User] = relationship(lazy="joined")
    location: Mapped[Location] = relationship(lazy="joined")


class InvItem(TimestampMixin, Base):
    __tablename__ = "inv_items"
    __table_args__ = (Index("ix_inv_items_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("inv_categories.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("inv_models.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    holder_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    delivery_id: Mapped[int | None] = mapped_column(ForeignKey("inv_deliveries.id"))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Deleting hides an item from lists and searches; the item and its history are kept.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    delete_reason: Mapped[str | None] = mapped_column(Text)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    category: Mapped[InvCategory] = relationship(lazy="joined")
    model: Mapped[InvModel] = relationship(lazy="joined")
    project: Mapped[Project] = relationship(lazy="joined")
    location: Mapped[Location] = relationship(lazy="joined")
    holder: Mapped[User | None] = relationship(foreign_keys=[holder_user_id], lazy="joined")
    delivery: Mapped[InvDelivery | None] = relationship(lazy="select")


class InvMovement(Base):
    """One change to one item. Rows are only ever added, never updated or deleted."""

    __tablename__ = "inv_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    from_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    to_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    delivery_id: Mapped[int | None] = mapped_column(ForeignKey("inv_deliveries.id"))
    withdrawal_id: Mapped[int | None] = mapped_column(ForeignKey("inv_withdrawals.id"))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    actor: Mapped[User] = relationship(lazy="joined")
    from_location: Mapped[Location | None] = relationship(foreign_keys=[from_location_id], lazy="joined")
    to_location: Mapped[Location | None] = relationship(foreign_keys=[to_location_id], lazy="joined")
    delivery: Mapped[InvDelivery | None] = relationship(lazy="joined")


class InvWithdrawal(TimestampMixin, Base):
    """A request to take items of one project out of stock to a new location."""

    __tablename__ = "inv_withdrawals"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    to_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    project: Mapped[Project] = relationship(lazy="joined")
    requester: Mapped[User] = relationship(lazy="joined")
    to_location: Mapped[Location] = relationship(lazy="joined")
    lines: Mapped[list[InvWithdrawalItem]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", back_populates="withdrawal"
    )
    tasks: Mapped[list[InvWithdrawalTask]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="withdrawal",
        order_by="InvWithdrawalTask.id",
    )


class InvWithdrawalItem(Base):
    __tablename__ = "inv_withdrawal_items"

    withdrawal_id: Mapped[int] = mapped_column(
        ForeignKey("inv_withdrawals.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), primary_key=True, index=True)

    withdrawal: Mapped[InvWithdrawal] = relationship(back_populates="lines")
    item: Mapped[InvItem] = relationship(lazy="joined")


class InvWithdrawalTask(Base):
    """One approval step (project PM, then operations manager) of one round of a withdrawal."""

    __tablename__ = "inv_withdrawal_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    withdrawal_id: Mapped[int] = mapped_column(
        ForeignKey("inv_withdrawals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    """PENDING, APPROVED, REJECTED, SKIPPED or CLOSED."""
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    withdrawal: Mapped[InvWithdrawal] = relationship(back_populates="tasks")
    decided_by: Mapped[User | None] = relationship(lazy="joined")


class InvWithdrawalEvent(Base):
    """What happened to a withdrawal request, in order. Only ever added to."""

    __tablename__ = "inv_withdrawal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    withdrawal_id: Mapped[int] = mapped_column(
        ForeignKey("inv_withdrawals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    actor: Mapped[User] = relationship(lazy="joined")
