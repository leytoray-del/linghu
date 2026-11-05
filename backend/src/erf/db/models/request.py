from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from erf.db.base import Base, TimestampMixin
from erf.domain.enums import RequestStatus

if TYPE_CHECKING:
    from erf.db.models.team import SupportType, Team
    from erf.db.models.user import User
    from erf.db.models.workflow import ApprovalTask, RequestChange, RequestEvent, ResourceAllocation


class ResourceRequest(TimestampMixin, Base):
    """One engineering resource request. Column comments map to the original form's question numbers."""

    __tablename__ = "resource_requests"
    __table_args__ = (
        CheckConstraint("headcount IS NULL OR headcount > 0", name="headcount_positive"),
        CheckConstraint("man_days IS NULL OR man_days > 0", name="man_days_positive"),
        CheckConstraint(
            "planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start", name="date_order"
        ),
        CheckConstraint("status = 'DRAFT' OR request_no IS NOT NULL", name="submitted_has_number"),
        Index("ix_requests_status_team", "status", "team_id"),
        Index("ix_requests_requester_status", "requester_id", "status"),
        Index("ix_requests_period", "planned_start", "planned_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_no: Mapped[str | None] = mapped_column(String(32), unique=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RequestStatus.DRAFT.value)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    request_type: Mapped[str | None] = mapped_column(String(16))  # Q1
    priority_declared: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")  # Q2
    is_urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    urgency_reason: Mapped[str | None] = mapped_column(String(16))
    notice_working_days: Mapped[int | None] = mapped_column(Integer)
    project_name: Mapped[str | None] = mapped_column(String(200))  # Q3
    wbs_code: Mapped[str | None] = mapped_column(String(64))  # Q4
    client_name: Mapped[str | None] = mapped_column(String(200))  # Q5
    support_type_id: Mapped[int | None] = mapped_column(ForeignKey("support_types.id"))  # Q6
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    headcount: Mapped[int | None] = mapped_column(Integer)  # Q7
    preferred_engineers_note: Mapped[str | None] = mapped_column(String(500))  # Q8
    man_days: Mapped[float | None] = mapped_column(Float)  # Q9
    planned_start: Mapped[date | None] = mapped_column(Date)  # Q10
    planned_end: Mapped[date | None] = mapped_column(Date)  # Q11
    scope_description: Mapped[str | None] = mapped_column(Text)  # Q12
    task_schedule: Mapped[str | None] = mapped_column(Text)  # Q13
    urgent_justification: Mapped[str | None] = mapped_column(Text)  # Q14

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    requester: Mapped[User] = relationship(lazy="joined", foreign_keys=[requester_id])
    support_type: Mapped[SupportType | None] = relationship(lazy="joined")
    team: Mapped[Team | None] = relationship(lazy="joined")
    preferred_rows: Mapped[list[RequestPreferredEngineer]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    tasks: Mapped[list[ApprovalTask]] = relationship(
        back_populates="request", lazy="selectin", order_by="ApprovalTask.id", cascade="all, delete-orphan"
    )
    allocations: Mapped[list[ResourceAllocation]] = relationship(
        back_populates="request",
        lazy="selectin",
        order_by="ResourceAllocation.id",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[RequestEvent]] = relationship(
        back_populates="request", lazy="selectin", order_by="RequestEvent.id", cascade="all, delete-orphan"
    )

    changes: Mapped[list[RequestChange]] = relationship(
        back_populates="request", lazy="selectin", order_by="RequestChange.id", cascade="all, delete-orphan"
    )

    @property
    def status_enum(self) -> RequestStatus:
        return RequestStatus(self.status)

    @property
    def preferred_engineer_ids(self) -> list[int]:
        return [p.user_id for p in self.preferred_rows]

    @property
    def display_no(self) -> str:
        return self.request_no or f"DRAFT-{self.id}"


class RequestPreferredEngineer(Base):
    __tablename__ = "request_preferred_engineers"

    request_id: Mapped[int] = mapped_column(
        ForeignKey("resource_requests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
