"""Cross-field validation applied when a request is submitted. Drafts may be incomplete."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from erf.domain.enums import RequestType

MAX_HEADCOUNT = 50


@dataclass(slots=True)
class SubmissionFields:
    request_type: RequestType | None
    project_name: str | None
    client_name: str | None
    support_type_id: int | None
    headcount: int | None
    man_days: float | None
    planned_start: date | None
    planned_end: date | None
    scope_description: str | None
    task_schedule: str | None
    is_urgent: bool
    urgent_justification: str | None


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def validate_submission(f: SubmissionFields, today: date) -> dict[str, str]:
    """Return a mapping of field name to a message that tells the user how to fix it."""
    errors: dict[str, str] = {}
    if f.request_type is None:
        errors["request_type"] = "Choose the request type."
    if _blank(f.project_name):
        errors["project_name"] = "Enter the project or opportunity name."
    if _blank(f.client_name):
        errors["client_name"] = "Enter the client name."
    if f.support_type_id is None:
        errors["support_type_id"] = "Choose the type of support."
    if f.headcount is None or f.headcount < 1:
        errors["headcount"] = "Enter how many engineers or developers you need (at least 1)."
    elif f.headcount > MAX_HEADCOUNT:
        errors["headcount"] = f"A single request can ask for at most {MAX_HEADCOUNT} people."
    if f.request_type == RequestType.PROJECT and (f.man_days is None or f.man_days <= 0):
        errors["man_days"] = "Enter the awarded man-days. This is required for project requests."
    if f.man_days is not None and f.man_days <= 0:
        errors["man_days"] = "Man-days must be greater than zero."
    if f.planned_start is None:
        errors["planned_start"] = "Enter the planned start date."
    elif f.planned_start < today:
        errors["planned_start"] = "The planned start date cannot be in the past."
    if f.planned_end is None:
        errors["planned_end"] = "Enter the planned end date."
    elif f.planned_start is not None and f.planned_end < f.planned_start:
        errors["planned_end"] = "The planned end date must be on or after the start date."
    if _blank(f.scope_description):
        errors["scope_description"] = "Describe the scope of work."
    if _blank(f.task_schedule):
        errors["task_schedule"] = "Describe the task schedule and timing."
    if f.is_urgent and _blank(f.urgent_justification):
        errors["urgent_justification"] = "Explain why this request is urgent."
    return errors
