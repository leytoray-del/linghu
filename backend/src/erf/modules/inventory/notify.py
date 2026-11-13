"""Emails about withdrawal requests, queued in the shared email outbox."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from erf.db.models import NotificationOutbox, User
from erf.domain.enums import OutboxStatus
from erf.modules.inventory.domain import WithdrawalStep
from erf.modules.inventory.models import InvWithdrawal
from erf.services.context import ServiceContext

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
    autoescape=select_autoescape(["html"]),
)
STEP_NAME = {WithdrawalStep.PM: "project manager", WithdrawalStep.OM: "operations manager"}


class WithdrawalMail:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx

    def _queue(
        self,
        event: str,
        w: InvWithdrawal,
        to: Iterable[User],
        *,
        subject: str,
        heading: str,
        message: str,
        button: str,
        actor: User | None = None,
        comment: str | None = None,
        cc: Iterable[User] = (),
    ) -> None:
        to_list = list(dict.fromkeys(u.email for u in to if u.is_active and u.email))
        cc_list = [
            e for e in dict.fromkeys(u.email for u in cc if u.is_active and u.email) if e not in to_list
        ]
        if not to_list:
            return
        context = {
            "app_name": self.ctx.settings.app_name,
            "heading": heading,
            "message": message,
            "button": button,
            "link": f"{self.ctx.settings.base_url.rstrip('/')}/inventory/withdrawals/{w.id}",
            "actor": actor.display_name if actor else "",
            "comment": comment,
            "w": w,
            "items": sorted((line.item for line in w.lines), key=lambda i: i.serial_no),
        }
        self.ctx.session.add(
            NotificationOutbox(
                event_type=event,
                request_id=None,
                to_addresses=json.dumps(to_list),
                cc_addresses=json.dumps(cc_list),
                subject=subject[:255],
                body_html=_env.get_template("withdrawal.html").render(**context),
                body_text=_env.get_template("withdrawal.txt").render(**context),
                status=OutboxStatus.PENDING.value,
                next_attempt_at=self.ctx.clock.now(),
            )
        )

    def waiting(self, w: InvWithdrawal, approvers: list[User], step: WithdrawalStep) -> None:
        n = len(w.lines)
        self._queue(
            "WITHDRAWAL_WAITING",
            w,
            approvers,
            subject=f"{w.request_no} needs your approval: {n} item{'s' if n != 1 else ''} for {w.project.name}",
            heading="A withdrawal needs your approval",
            message=(
                f"{w.requester.display_name} asks to move {n} item{'s' if n != 1 else ''} of {w.project.name} "
                f"to {w.to_location.name}. Your approval as {STEP_NAME[step]} is needed."
            ),
            button="Review the request",
        )

    def rejected(self, w: InvWithdrawal, actor: User, comment: str) -> None:
        self._queue(
            "WITHDRAWAL_REJECTED",
            w,
            [w.requester],
            subject=f"{w.request_no} rejected: {w.project.name}",
            heading="Your withdrawal was rejected",
            message=f"{actor.display_name} rejected the request. You can revise it and submit it again, or withdraw it. "
            "The items are back in stock in the meantime.",
            button="Revise or withdraw",
            actor=actor,
            comment=comment,
        )

    def approved(self, w: InvWithdrawal, actor: User) -> None:
        n = len(w.lines)
        self._queue(
            "WITHDRAWAL_APPROVED",
            w,
            [w.requester],
            cc=[w.project.pm] if w.project.pm else [],
            subject=f"{w.request_no} approved: {n} item{'s' if n != 1 else ''} to {w.to_location.name}",
            heading="Your withdrawal was approved",
            message=f"{actor.display_name} gave the final approval. The {n} item{'s are' if n != 1 else ' is'} now "
            f"recorded at {w.to_location.name}.",
            button="Open the request",
            actor=actor,
        )
