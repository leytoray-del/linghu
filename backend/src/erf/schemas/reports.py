from __future__ import annotations

from datetime import date

from erf.schemas.common import Schema, UserRef
from erf.schemas.requests import SupportTypeBrief


class Lookups(Schema):
    support_types: list[SupportTypeBrief]
    teams: list[dict[str, object]]
    directors: list[str]
    min_notice_working_days: int
    today: date


class LoadAssignment(Schema):
    request_id: int
    display_no: str
    project_name: str | None
    client_name: str | None
    start_date: date
    end_date: date
    status: str


class EngineerLoad(Schema):
    engineer: UserRef
    team_id: int | None
    team_name: str | None
    skills: str | None
    assignments: list[LoadAssignment]


class LoadOut(Schema):
    start: date
    end: date
    engineers: list[EngineerLoad]


class MonthCount(Schema):
    month: str
    normal: int
    urgent: int


class NamedCount(Schema):
    name: str
    count: int


class ReportSummary(Schema):
    year: int
    total: int
    urgent: int
    urgent_share: float
    approved: int
    approved_man_days: float
    median_tl_hours: float | None
    median_director_hours: float | None
    by_month: list[MonthCount]
    by_status: list[NamedCount]
    by_support_type: list[NamedCount]
    by_team: list[NamedCount]


class DashboardOut(Schema):
    my_open: int
    my_returned: int
    my_approved: int
    my_drafts: int
    my_total: int
    pending_tasks: int
    pending_urgent: int
    overdue_tasks: int
    team_requests_open: int
    assigned_active: int
