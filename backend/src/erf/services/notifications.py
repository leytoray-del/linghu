"""Turns workflow events into rendered emails in the outbox. Delivery happens in a background job."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from erf.db.models import NotificationOutbox, ResourceRequest, User
from erf.domain.enums import OutboxStatus, RequestType
from erf.infrastructure.mail.senders import Attachment
from erf.repositories.requests import OutboxRepository
from erf.repositories.users import UserRepository
from erf.services.action_links import ActionLink
from erf.services.context import ServiceContext

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"


class Event(StrEnum):
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    TL_APPROVED = "TL_APPROVED"
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_RETURNED = "REQUEST_RETURNED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    REQUEST_WITHDRAWN = "REQUEST_WITHDRAWN"
    REQUEST_CANCELLED = "REQUEST_CANCELLED"
    TASK_REMINDER = "TASK_REMINDER"
    CHANGE_REQUESTED = "CHANGE_REQUESTED"
    CHANGE_APPROVED = "CHANGE_APPROVED"
    CHANGE_REJECTED = "CHANGE_REJECTED"


@dataclass(frozen=True, slots=True)
class EventText:
    subject: str
    heading: str
    message: str
    button: str


EVENT_TEXT: dict[Event, EventText] = {
    Event.CHANGE_REQUESTED: EventText(
        "{no} change needs your review: {project}",
        "A change to an approved request needs your review",
        "{actor} asked to change this approved request: {change}. Review the engineers and approve or reject "
        "the change.",
        "Review change",
    ),
    Event.CHANGE_APPROVED: EventText(
        "{no} change approved: {project}",
        "A change to an approved request was approved",
        "{actor} approved the change: {change}. The allocation below is now confirmed.",
        "View request",
    ),
    Event.CHANGE_REJECTED: EventText(
        "{no} change rejected: {project}",
        "Your change request was rejected",
        "{actor} rejected the change: {change}. The request keeps its current dates and engineers.",
        "View request",
    ),
    Event.REQUEST_SUBMITTED: EventText(
        "{no} needs your review: {project}",
        "A resource request needs your review",
        "{actor} submitted a request for {headcount} × {support_type}. Please review it, assign engineers "
        "from your team and approve, return or reject it.",
        "Review request",
    ),
    Event.TL_APPROVED: EventText(
        "{no} needs your approval: {project}",
        "A resource request needs your approval",
        "{actor} reviewed this request and proposed the allocation below. Please give the final decision.",
        "Open request",
    ),
    Event.REQUEST_APPROVED: EventText(
        "{no} approved: {project}",
        "Resource request approved",
        "The request has been approved and the allocation below is confirmed.",
        "View request",
    ),
    Event.REQUEST_RETURNED: EventText(
        "{no} returned for revision: {project}",
        "Your request was returned for revision",
        "{actor} returned your request. Update it based on the comment below and resubmit it.",
        "Revise request",
    ),
    Event.REQUEST_REJECTED: EventText(
        "{no} rejected: {project}",
        "Your request was rejected",
        "{actor} rejected this request. If the need still exists, raise a new request.",
        "View request",
    ),
    Event.REQUEST_WITHDRAWN: EventText(
        "{no} withdrawn: {project}",
        "A request was withdrawn",
        "{actor} withdrew this request. No further action is needed, and any proposed engineers are released.",
        "View request",
    ),
    Event.REQUEST_CANCELLED: EventText(
        "{no} cancelled: {project}",
        "An approved request was cancelled",
        "{actor} cancelled this approved request. The engineers below are released from it.",
        "View request",
    ),
    Event.TASK_REMINDER: EventText(
        "Reminder: {no} is waiting for you: {project}",
        "A request is still waiting for your decision",
        "This request has been waiting since {waiting_since}. Please review it.",
        "Open request",
    ),
}

CHANGE_EVENTS = frozenset({Event.CHANGE_REQUESTED, Event.CHANGE_APPROVED, Event.CHANGE_REJECTED})

REQUEST_TYPE_LABEL = {
    RequestType.PROJECT.value: "Project",
    RequestType.PRESALES.value: "Pre-sales",
    "OTHER": "Other",
}


class NotificationService:
    _env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))

    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.outbox = OutboxRepository(ctx.session)

    def notify(
        self,
        event: Event,
        request: ResourceRequest,
        *,
        to: Iterable[User],
        cc: Iterable[User] = (),
        actor: User | None = None,
        comment: str | None = None,
        extra: dict[str, str] | None = None,
        attachments: list[Attachment] | None = None,
        actions: list[ActionLink] | None = None,
        copy_of: list[User] | None = None,
    ) -> NotificationOutbox | None:
        """Queue one email. ``actions`` adds approve, return and reject buttons (only for the approver the
        links belong to). ``copy_of`` marks an information copy of an email sent to those people."""
        to_list = _addresses(to)
        cc_list = [a for a in _addresses(cc) if a not in to_list]
        if not to_list:
            return None
        text = EVENT_TEXT[event]
        fields = {
            "no": request.display_no,
            "project": request.project_name or "(untitled)",
            "actor": actor.display_name if actor else "The system",
            "headcount": str(request.headcount or "?"),
            "support_type": request.support_type.name if request.support_type else "engineers",
            **(extra or {}),
        }
        subject = text.subject.format(**fields)
        if request.is_urgent:
            subject = f"[URGENT] {subject}"
        context = {
            "app_name": self.ctx.settings.app_name,
            "heading": text.heading,
            "message": text.message.format(**fields),
            "comment": comment,
            "actor": fields["actor"],
            "button": text.button,
            "link": f"{self.ctx.settings.base_url.rstrip('/')}/requests/{request.id}",
            "r": request,
            "request_type": REQUEST_TYPE_LABEL.get(request.request_type or "", "—"),
            "allocations": [a for a in request.allocations if a.status != "RELEASED"],
            "preferred": [
                u.display_name
                for u in UserRepository(self.ctx.session).get_many(request.preferred_engineer_ids)
            ],
            "change": request.changes[-1] if event in CHANGE_EVENTS and request.changes else None,
            "actions": actions or [],
            "copy_of": ", ".join(u.display_name for u in copy_of) if copy_of else None,
        }
        row = NotificationOutbox(
            event_type=event.value,
            request_id=request.id,
            to_addresses=json.dumps(to_list),
            cc_addresses=json.dumps(cc_list),
            subject=subject[:255],
            body_html=self._env.get_template("notification.html").render(**context),
            body_text=self._env.get_template("notification.txt").render(**context),
            status=OutboxStatus.PENDING.value,
            next_attempt_at=self.ctx.clock.now(),
            attachments=json.dumps([asdict(a) for a in attachments]) if attachments else None,
        )
        self.outbox.add(row)
        return row


def _addresses(users: Iterable[User]) -> list[str]:
    seen: list[str] = []
    for u in users:
        if u.is_active and u.email and u.email not in seen:
            seen.append(u.email)
    return seen


def _nl2br(value: object) -> Markup:
    """Keep line breaks of long text fields such as the scope description in HTML emails."""
    return Markup("<br>").join(escape(str(value or "")).split("\n"))


NotificationService._env.filters["nl2br"] = _nl2br
