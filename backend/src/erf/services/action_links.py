"""Builds the signed approve, return and reject links placed in emails to approvers."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, timedelta

from erf.core.action_tokens import make_token
from erf.db.models import ApprovalTask, SystemSetting
from erf.domain.enums import ApprovalStep
from erf.services.context import ServiceContext

SECRET_KEY = "email_action_secret"
"""Stored in system_settings; generated on first use. It is not one of the editable settings."""


@dataclass(frozen=True, slots=True)
class ActionLink:
    label: str
    url: str
    style: str
    """primary, neutral or danger: how the button is drawn in the email."""


def action_secret(ctx: ServiceContext) -> bytes:
    row = ctx.session.get(SystemSetting, SECRET_KEY)
    if row is None:
        row = SystemSetting(
            key=SECRET_KEY, value=secrets.token_hex(32), description="Signs email action links."
        )
        ctx.session.add(row)
        ctx.session.flush()
    return bytes.fromhex(row.value)


def task_token(ctx: ServiceContext, task: ApprovalTask) -> str:
    days = ctx.config.get_int("email_link_valid_days")
    expires = int((ctx.clock.now() + timedelta(days=days)).replace(tzinfo=UTC).timestamp())
    return make_token(action_secret(ctx), task.id, expires)


def links_for(ctx: ServiceContext, task: ApprovalTask) -> list[ActionLink]:
    """The buttons for one approver's task. Each opens a confirmation page; nothing happens on opening."""
    base = f"{ctx.settings.base_url.rstrip('/')}/act/{task_token(ctx, task)}"
    if task.step == ApprovalStep.CHANGE_REVIEW.value:
        return [
            ActionLink("Approve change", f"{base}?do=approve", "primary"),
            ActionLink("Reject change", f"{base}?do=reject", "danger"),
        ]
    if task.step == ApprovalStep.DIRECTOR_APPROVAL.value:
        # Every decision needs a click on the page. Mail security gateways open links in full browsers
        # that run scripts, so a link that approves by itself can be triggered by a scanner.
        return [
            ActionLink("Approve", f"{base}?do=approve", "primary"),
            ActionLink("Return to requester", f"{base}?do=return", "neutral"),
            ActionLink("Reject", f"{base}?do=reject", "danger"),
        ]
    return [
        ActionLink("Approve and assign engineers", f"{base}?do=approve", "primary"),
        ActionLink("Return to requester", f"{base}?do=return", "neutral"),
        ActionLink("Reject", f"{base}?do=reject", "danger"),
    ]


def review_url(ctx: ServiceContext, task: ApprovalTask) -> str:
    """The confirmation page for a task without a preselected decision."""
    return f"{ctx.settings.base_url.rstrip('/')}/act/{task_token(ctx, task)}"
