"""The request state machine.

Every status change must match one row of ``TRANSITIONS``. The service layer resolves *who* may act
(requester, current step assignee, administrator, system); this module only defines *what* is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from erf.core.errors import InvalidTransition
from erf.domain.enums import Action, ApprovalStep, RequestStatus

S = RequestStatus


class Actor(StrEnum):
    REQUESTER = "REQUESTER"
    STEP_ASSIGNEE = "STEP_ASSIGNEE"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True, slots=True)
class Transition:
    source: RequestStatus
    action: Action
    target: RequestStatus
    actors: frozenset[Actor]
    requires_comment: bool = False


def _t(
    source: RequestStatus, action: Action, target: RequestStatus, *actors: Actor, comment: bool = False
) -> Transition:
    return Transition(source, action, target, frozenset(actors), comment)


TRANSITIONS: tuple[Transition, ...] = (
    _t(S.DRAFT, Action.SUBMIT, S.PENDING_TL_REVIEW, Actor.REQUESTER),
    _t(S.RETURNED, Action.SUBMIT, S.PENDING_TL_REVIEW, Actor.REQUESTER),
    _t(S.PENDING_TL_REVIEW, Action.APPROVE, S.PENDING_DIRECTOR_APPROVAL, Actor.STEP_ASSIGNEE),
    _t(S.PENDING_TL_REVIEW, Action.RETURN, S.RETURNED, Actor.STEP_ASSIGNEE, comment=True),
    _t(S.PENDING_TL_REVIEW, Action.REJECT, S.REJECTED, Actor.STEP_ASSIGNEE, comment=True),
    _t(S.PENDING_DIRECTOR_APPROVAL, Action.APPROVE, S.APPROVED, Actor.STEP_ASSIGNEE),
    _t(S.PENDING_DIRECTOR_APPROVAL, Action.RETURN, S.RETURNED, Actor.STEP_ASSIGNEE, comment=True),
    _t(S.PENDING_DIRECTOR_APPROVAL, Action.REJECT, S.REJECTED, Actor.STEP_ASSIGNEE, comment=True),
    _t(S.PENDING_TL_REVIEW, Action.WITHDRAW, S.WITHDRAWN, Actor.REQUESTER, Actor.ADMIN),
    _t(S.PENDING_DIRECTOR_APPROVAL, Action.WITHDRAW, S.WITHDRAWN, Actor.REQUESTER, Actor.ADMIN),
    _t(S.RETURNED, Action.WITHDRAW, S.WITHDRAWN, Actor.REQUESTER, Actor.ADMIN),
    _t(S.APPROVED, Action.CANCEL, S.CANCELLED, Actor.REQUESTER, Actor.ADMIN, comment=True),
    _t(S.APPROVED, Action.CLOSE, S.CLOSED, Actor.REQUESTER, Actor.ADMIN, Actor.SYSTEM),
)

_INDEX: dict[tuple[RequestStatus, Action], Transition] = {(t.source, t.action): t for t in TRANSITIONS}

STEP_FOR_STATUS: dict[RequestStatus, ApprovalStep] = {
    S.PENDING_TL_REVIEW: ApprovalStep.TL_REVIEW,
    S.PENDING_DIRECTOR_APPROVAL: ApprovalStep.DIRECTOR_APPROVAL,
}


_VERB: dict[Action, str] = {
    Action.SUBMIT: "submit",
    Action.APPROVE: "approve",
    Action.RETURN: "reject",
    Action.REJECT: "reject",
    Action.WITHDRAW: "withdraw",
    Action.CANCEL: "cancel",
    Action.CLOSE: "close",
}

_STATE: dict[RequestStatus, str] = {
    S.DRAFT: "has not been submitted yet",
    S.PENDING_TL_REVIEW: "is waiting for the team leader",
    S.PENDING_DIRECTOR_APPROVAL: "is waiting for the director",
    S.RETURNED: "has been sent back to the requester",
    S.APPROVED: "has already been approved",
    S.REJECTED: "has been rejected permanently",
    S.WITHDRAWN: "has been withdrawn",
    S.CANCELLED: "has been cancelled",
    S.CLOSED: "is closed",
}


def find_transition(source: RequestStatus, action: Action) -> Transition:
    transition = _INDEX.get((source, action))
    if transition is None:
        raise InvalidTransition(
            f"You cannot {_VERB[action]} this request now because it {_STATE[source]}. "
            "Refresh the page to see its latest progress.",
            details={"status": source.value, "action": action.value},
        )
    return transition


def available_actions(source: RequestStatus, actors: set[Actor]) -> list[Action]:
    """Actions the given set of actor capacities may perform from ``source``."""
    return [t.action for t in TRANSITIONS if t.source == source and t.actors & actors]
