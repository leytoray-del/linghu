from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from erf.db.base import Base, TimestampMixin, utcnow

if TYPE_CHECKING:
    from erf.db.models.request import ResourceRequest
    from erf.db.models.user import User


class ApprovalTask(TimestampMixin, Base):
    """A to-do for one approver at one workflow step of one submission round."""

    __tablename__ = "approval_tasks"
    __table_args__ = (Index("ix_tasks_assignee_status", "assignee_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("resource_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_comment: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime)

    request: Mapped[ResourceRequest] = relationship(back_populates="tasks")
    assignee: Mapped[User] = relationship(lazy="joined")


class ResourceAllocation(TimestampMixin, Base):
    __tablename__ = "resource_allocations"
    __table_args__ = (
        Index(
            "uq_allocation_active_engineer",
            "request_id",
            "engineer_id",
            unique=True,
            sqlite_where=text("status != 'RELEASED'"),
            postgresql_where=text("status != 'RELEASED'"),
        ),
        Index("ix_allocations_engineer_period", "engineer_id", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("resource_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engineer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    allocation_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    allocated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    request: Mapped[ResourceRequest] = relationship(back_populates="allocations")
    engineer: Mapped[User] = relationship(lazy="joined", foreign_keys=[engineer_id])


class RequestEvent(Base):
    """Append-only audit trail of everything that happened to a request."""

    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("resource_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    request: Mapped[ResourceRequest] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship(lazy="joined")


class NotificationOutbox(TimestampMixin, Base):
    """Emails written in the same transaction as the business change and delivered by a background job."""

    __tablename__ = "notification_outbox"
    __table_args__ = (Index("ix_outbox_status_next", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("resource_requests.id", ondelete="SET NULL"))
    to_addresses: Mapped[str] = mapped_column(Text, nullable=False)
    cc_addresses: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
