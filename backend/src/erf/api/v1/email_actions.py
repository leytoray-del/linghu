"""Public endpoints behind the approve, return and reject links in emails. The signed link authenticates
the approver, so these routes need no session and no CSRF token."""

from __future__ import annotations

from fastapi import APIRouter

from erf.api.deps import Ctx
from erf.schemas.requests import EmailActionIn, EmailActionOut, EmailActionResult
from erf.services.email_action_service import EmailActionService

router = APIRouter(prefix="/email-actions", tags=["email actions"])


@router.get("/{token}", response_model=EmailActionOut)
def view_action(token: str, ctx: Ctx) -> EmailActionOut:
    return EmailActionService(ctx).view(token)


@router.post("/{token}", response_model=EmailActionResult)
def perform_action(token: str, body: EmailActionIn, ctx: Ctx) -> EmailActionResult:
    return EmailActionService(ctx).act(token, body.action, body.comment, body.allocations)
