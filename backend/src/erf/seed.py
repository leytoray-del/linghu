"""Reference data and demo data.

Reference data (teams, support types, holidays, settings) is needed by every installation.
Demo data (accounts and requests) is for evaluation only. Demo requests are created through the real
services with a simulated clock, so their history, tasks and allocations are exactly what users would
have produced.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erf.core.clock import Clock, FixedClock
from erf.core.config import Settings
from erf.core.security import hash_password
from erf.db.models import Holiday, NotificationOutbox, ResourceRequest, SupportType, Team, TeamApprover, User
from erf.domain.enums import Action, OutboxStatus, Priority, RequestType, Role
from erf.modules.inventory.seed import seed_inventory_demo, seed_inventory_reference
from erf.schemas.requests import RequestIn
from erf.services.context import ServiceContext
from erf.services.request_service import RequestService
from erf.services.role_service import ensure_roles
from erf.services.workflow_service import WorkflowService

log = logging.getLogger(__name__)

DEMO_PASSWORD = "Demo@2026!"

TEAMS = [("SUPPORT", "Support Team"), ("DEV", "Development Team")]

# Placeholder list: confirm the real "Type of support" options with the business.
SUPPORT_TYPES = [
    ("PE", "Project Engineer", "SUPPORT", 10),
    ("SE", "Support Engineer", "SUPPORT", 20),
    ("ONSITE", "On-site Support", "SUPPORT", 30),
    ("DEV", "Developer", "DEV", 40),
    ("SA", "Solution Architect", "DEV", 50),
]

# Singapore public holidays. Verify each year against the official Ministry of Manpower list.
HOLIDAYS = [
    ("2026-01-01", "New Year's Day"),
    ("2026-02-17", "Chinese New Year"),
    ("2026-02-18", "Chinese New Year (second day)"),
    ("2026-03-21", "Hari Raya Puasa"),
    ("2026-04-03", "Good Friday"),
    ("2026-05-01", "Labour Day"),
    ("2026-05-27", "Hari Raya Haji"),
    ("2026-06-01", "Vesak Day (observed)"),
    ("2026-08-10", "National Day (observed)"),
    ("2026-11-09", "Deepavali (observed)"),
    ("2026-12-25", "Christmas Day"),
    ("2027-01-01", "New Year's Day"),
    ("2027-02-08", "Chinese New Year (observed)"),
    ("2027-03-26", "Good Friday"),
    ("2027-08-09", "National Day"),
    ("2027-12-25", "Christmas Day"),
]


@dataclass(frozen=True)
class DemoUser:
    key: str
    email: str
    name: str
    title: str
    roles: tuple[Role, ...]
    team: str | None = None
    skills: str | None = None


DEMO_USERS = [
    DemoUser("admin", "admin@example.com", "Lee Wei Jie", "System Administrator", (Role.ADMIN,)),
    DemoUser("director", "grace.wong@example.com", "Grace Wong", "Director, Engineering", (Role.DIRECTOR,)),
    DemoUser("tl_support", "priya.nair@example.com", "Priya Nair", "Team Leader, Support", (Role.TEAM_LEADER,), "SUPPORT"),
    DemoUser("tl_dev", "daniel.lim@example.com", "Daniel Lim", "Team Leader, Development", (Role.TEAM_LEADER,), "DEV"),
    DemoUser("pm1", "alex.tan@example.com", "Alex Tan", "Project Manager", ()),
    DemoUser("pm2", "serene.koh@example.com", "Serene Koh", "Project Manager", ()),
    DemoUser("pmo", "pmo@example.com", "Rachel Goh", "PMO Analyst", (Role.VIEWER,)),
    DemoUser("e_ahmad", "ahmad.rahman@example.com", "Ahmad Rahman", "Senior Engineer", (Role.ENGINEER,), "SUPPORT", "Network, on-site"),
    DemoUser("e_meiling", "meiling.chua@example.com", "Chua Mei Ling", "Engineer", (Role.ENGINEER,), "SUPPORT", "Data migration"),
    DemoUser("e_kevin", "kevin.ong@example.com", "Kevin Ong", "Engineer", (Role.ENGINEER,), "SUPPORT", "Server, storage"),
    DemoUser("e_nurul", "nurul.huda@example.com", "Nurul Huda", "Engineer", (Role.ENGINEER,), "SUPPORT", "Service desk, Wi-Fi"),
    DemoUser("e_ravi", "ravi.kumar@example.com", "Ravi Kumar", "Senior Developer", (Role.ENGINEER,), "DEV", "Java, integration"),
    DemoUser("e_jason", "jason.teo@example.com", "Jason Teo", "Developer", (Role.ENGINEER,), "DEV", ".NET, web portal"),
    DemoUser("e_siti", "siti.aminah@example.com", "Siti Aminah", "Solution Architect", (Role.ENGINEER,), "DEV", "Solution design"),
    DemoUser("clerk", "muthu.selvam@example.com", "Muthu Selvam", "Support Engineer, Inventory", (Role.ENGINEER, Role.INVENTORY_CLERK), "SUPPORT", "Hardware, logistics"),
    DemoUser("ops", "wong.meifen@example.com", "Wong Mei Fen", "Operations Manager", (Role.OPS_MANAGER,)),
    DemoUser("e_marcus", "marcus.lee@example.com", "Marcus Lee", "Developer", (Role.ENGINEER,), "DEV", "Python, ETL"),
]  # fmt: skip

SCOPE_MIGRATION = (
    "- Configure the extraction script to limit processing to 100,000 records, based on the file list "
    "provided in the Excel source.\n"
    "- Enhance the extraction program, where necessary, to ingest and process the CSV output generated "
    "from the initial extraction step.\n"
    "- Coordinate with the ATFM team to securely transfer the required files for migration.\n"
    "- Perform reconciliation by tallying and validating the extracted and decrypted files to ensure "
    "completeness and accuracy.\n\nEstimated duration: 2 - 3 months"
)


def seed_reference(session: Session) -> None:
    """Create teams, support types and holidays if they do not exist. Safe to run repeatedly."""
    teams = {t.code: t for t in session.scalars(select(Team))}
    for code, name in TEAMS:
        if code not in teams:
            teams[code] = Team(code=code, name=name, is_active=True)
            session.add(teams[code])
    session.flush()
    existing_types = set(session.scalars(select(SupportType.code)))
    for code, name, team, order in SUPPORT_TYPES:
        if code not in existing_types:
            session.add(
                SupportType(code=code, name=name, team_id=teams[team].id, sort_order=order, is_active=True)
            )
    existing_days = set(session.scalars(select(Holiday.holiday_date)))
    for day, name in HOLIDAYS:
        d = date.fromisoformat(day)
        if d not in existing_days:
            session.add(Holiday(holiday_date=d, name=name))
    session.flush()


def seed_demo_users(session: Session) -> dict[str, User]:
    teams = {t.code: t for t in session.scalars(select(Team))}
    users: dict[str, User] = {}
    for spec in DEMO_USERS:
        user = session.scalar(select(User).where(User.email == spec.email))
        if user is None:
            user = User(
                email=spec.email,
                display_name=spec.name,
                job_title=spec.title,
                team_id=teams[spec.team].id if spec.team else None,
                skills=spec.skills,
                password_hash=hash_password(DEMO_PASSWORD),
                is_active=True,
                must_change_password=False,
            )
            user.set_roles({Role.REQUESTER, *spec.roles})
            session.add(user)
        users[spec.key] = user
    session.flush()
    for code, key in (("SUPPORT", "tl_support"), ("DEV", "tl_dev")):
        team = teams[code]
        if not team.approver_rows:
            team.approver_rows.append(TeamApprover(user_id=users[key].id))
    session.flush()
    return users


class _DemoBuilder:
    def __init__(self, session: Session, settings: Settings, today: date, users: dict[str, User]):
        self.s = session
        self.settings = settings
        self.today = today
        self.users = users
        self.clock = FixedClock(settings.timezone, datetime.now(UTC).replace(tzinfo=None))
        self.ctx = ServiceContext(session, self.clock, settings)
        self.types = {t.code: t.id for t in session.scalars(select(SupportType))}

    def at(self, days: int, hour: int = 10, minute: int = 0) -> None:
        local = datetime.combine(self.today + timedelta(days=days), time(hour, minute), tzinfo=self.clock.tz)
        self.clock.set(local.astimezone(UTC).replace(tzinfo=None))

    def day(self, offset: int) -> date:
        """A working day near ``today + offset`` (moved forward off weekends)."""
        d = self.today + timedelta(days=offset)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    def draft(self, who: str, **fields: object) -> ResourceRequest:
        return RequestService(self.ctx).create_draft(self.users[who], RequestIn(**fields))

    def submit(self, who: str, **fields: object) -> ResourceRequest:
        request = self.draft(who, **fields)
        return WorkflowService(self.ctx).submit(self.users[who], request, request.version)

    def decide(
        self,
        who: str,
        r: ResourceRequest,
        action: Action,
        comment: str | None = None,
        engineers: tuple[str, ...] = (),
    ) -> None:
        WorkflowService(self.ctx).decide(
            self.users[who], r, action, comment=comment, version=r.version,
            engineer_ids=[self.users[e].id for e in engineers],
        )  # fmt: skip


def seed_demo_requests(session: Session, settings: Settings, users: dict[str, User], today: date) -> int:
    if session.scalar(select(ResourceRequest.id).limit(1)) is not None:
        log.info("Requests already exist; demo requests were not added")
        return 0
    b = _DemoBuilder(session, settings, today, users)
    t = b.types
    project = RequestType.PROJECT.value
    count = 0

    # 1. Closed: finished last month and closed automatically.
    b.at(-62, 9, 15)
    r = b.submit("pm1", request_type=project, project_name="Library Wi-Fi Site Survey", wbs_code="P26-0288",
                 client_name="NLB", support_type_id=t["SE"], headcount=1, man_days=12,
                 planned_start=b.day(-45), planned_end=b.day(-22),
                 scope_description="Survey Wi-Fi coverage at 6 branches and recommend access point placement.",
                 task_schedule="One branch per week, report at the end.")  # fmt: skip
    b.at(-61, 14, 20)
    b.decide("tl_support", r, Action.APPROVE, "Nurul has done the previous survey.", ("e_nurul",))
    b.at(-60, 11, 5)
    b.decide("director", r, Action.APPROVE)
    b.at(-20, 0, 20)
    WorkflowService(b.ctx).close(None, r)
    count += 1

    # 2. Approved and running now.
    b.at(-17, 9, 40)
    r = b.submit("pm2", request_type=project, project_name="Archive Storage Upgrade", wbs_code="P26-0310",
                 client_name="NLB", support_type_id=t["SE"], headcount=2, man_days=35,
                 planned_start=b.day(-3), planned_end=b.day(40),
                 scope_description="Upgrade the archive storage cluster and migrate 40 TB of digitised material.",
                 task_schedule="Two engineers, four days per week, cut-over on a weekend.")  # fmt: skip
    b.at(-16, 15, 10)
    b.decide("tl_support", r, Action.APPROVE, "Ahmad and Kevin assigned.", ("e_ahmad", "e_kevin"))
    b.at(-15, 10, 30)
    b.decide("director", r, Action.APPROVE, "Approved. Please keep the cut-over plan updated.")
    count += 1

    # 3. Withdrawn by the requester.
    b.at(-12, 11, 0)
    r = b.submit("pm2", request_type=RequestType.PRESALES.value, project_name="Mobile App Security Review",
                 client_name="HSA", support_type_id=t["DEV"], headcount=1,
                 planned_start=b.day(5), planned_end=b.day(12),
                 scope_description="Support the security review of the tender response.",
                 task_schedule="Five working days.")  # fmt: skip
    b.at(-11, 9, 30)
    WorkflowService(b.ctx).withdraw(
        b.users["pm2"], r, comment="Customer postponed the tender.", version=r.version
    )
    count += 1

    # 4. Returned to the requester for revision.
    b.at(-10, 16, 45)
    r = b.submit("pm1", request_type=project, project_name="Branch Network Refresh", wbs_code="P26-0351",
                 client_name="CSPL", support_type_id=t["ONSITE"], headcount=3, man_days=30,
                 planned_start=b.day(25), planned_end=b.day(43),
                 scope_description="Replace access switches at 12 branches and verify connectivity after each cut-over.",
                 task_schedule="Night work, two branches per night.")  # fmt: skip
    b.at(-9, 10, 15)
    b.decide("tl_support", r, Action.RETURN,
             "Please split the on-site schedule by branch and confirm whether weekend work is required. "
             "I cannot release three engineers for night work without that.")  # fmt: skip
    count += 1

    # 5. Approved, starting soon (pre-sales, no man-days).
    b.at(-9, 9, 5)
    r = b.submit("pm1", request_type=RequestType.PRESALES.value, project_name="Smart Library Kiosk PoC",
                 client_name="NLB", support_type_id=t["SA"], headcount=1,
                 planned_start=b.day(11), planned_end=b.day(22),
                 scope_description="Prepare the solution architecture and a working proof of concept for the kiosk tender.",
                 task_schedule="Two weeks, presentation to the customer at the end.")  # fmt: skip
    b.at(-8, 13, 0)
    b.decide("tl_dev", r, Action.APPROVE, "Siti will lead the PoC.", ("e_siti",))
    b.at(-7, 9, 50)
    b.decide("director", r, Action.APPROVE)
    count += 1

    # 6. Waiting for the director.
    b.at(-6, 10, 20)
    r = b.submit("pm2", request_type=project, project_name="HSA Lab Portal Enhancement", wbs_code="P26-0377",
                 client_name="HSA", support_type_id=t["DEV"], headcount=2, man_days=60,
                 planned_start=b.day(18), planned_end=b.day(110),
                 scope_description="Enhance the lab results portal with the new sample-tracking module and role-based dashboards.",
                 task_schedule="Two developers full time. UAT starts three weeks before the end date.")  # fmt: skip
    b.at(-4, 17, 5)
    b.decide("tl_dev", r, Action.APPROVE,
             "Ravi and Jason are free from the start date. Ravi rolls off the permit work in January.",
             ("e_ravi", "e_jason"))  # fmt: skip
    count += 1

    # 7. Waiting for the support team leader, already overdue.
    b.at(-5, 11, 30)
    b.submit("pm2", request_type=project, project_name="Helpdesk Platform Cut-over", wbs_code="P26-0402",
             client_name="CSPL", support_type_id=t["PE"], headcount=1, man_days=10,
             planned_start=b.day(20), planned_end=b.day(34),
             scope_description="Support the cut-over of the helpdesk platform and hypercare for two weeks.",
             task_schedule="On site on cut-over weekend, then remote support.")  # fmt: skip
    count += 1

    # 8. Rejected short-notice request.
    b.at(-2, 9, 0)
    r = b.submit("pm2", request_type=RequestType.OTHER.value, project_name="Internal Asset Audit",
                 client_name="Internal", support_type_id=t["SE"], headcount=1,
                 planned_start=b.day(4), planned_end=b.day(8),
                 scope_description="Physical audit of lab equipment.", task_schedule="One week.",
                 urgent_justification="Audit deadline set by finance.")  # fmt: skip
    b.at(-1, 11, 20)
    b.decide(
        "tl_support",
        r,
        Action.REJECT,
        "This is an operations task and should go through the facilities team, not engineering resources.",
    )
    count += 1

    # 9. Urgent request waiting for the support team leader.
    b.at(-1, 15, 40)
    b.submit("pm1", request_type=project, priority_declared=Priority.URGENT, project_name="CSPL Data Migration Phase 2",
             wbs_code="P26-0392", client_name="NLB", support_type_id=t["PE"], headcount=2, man_days=40,
             preferred_engineer_ids=[users["e_meiling"].id], planned_start=b.day(6), planned_end=b.day(85),
             scope_description=SCOPE_MIGRATION,
             task_schedule="To support NLB on site 3 times per week for 2 to 3 months.",
             urgent_justification="The customer brought the cut-over forward by two weeks after their steering "
             "committee. The migration window cannot move because the source system licence expires.")  # fmt: skip
    count += 1

    # 10. Normal request waiting for the development team leader.
    b.at(-1, 16, 10)
    b.submit("pm2", request_type=project, project_name="Permit Portal Integration", wbs_code="P26-0418",
             client_name="HSA", support_type_id=t["DEV"], headcount=1, man_days=25,
             preferred_engineer_ids=[users["e_ravi"].id], planned_start=b.day(25), planned_end=b.day(70),
             scope_description="Build the REST integration between the permit portal and the licensing back end.",
             task_schedule="Full time for seven weeks.")  # fmt: skip
    count += 1

    # 11. Draft not yet submitted.
    b.at(0, 9, 0)
    b.draft("pm1", request_type=project, project_name="Data Centre Migration Assessment", client_name="CSPL",
            support_type_id=t["SA"], headcount=1, planned_start=b.day(30), planned_end=b.day(45))  # fmt: skip
    count += 1

    session.flush()
    # Demo history must not send real emails.
    session.execute(
        update(NotificationOutbox)
        .where(NotificationOutbox.status == OutboxStatus.PENDING.value)
        .values(status=OutboxStatus.SKIPPED.value, last_error="Demo data: not delivered.")
    )
    return count


def seed_all(session: Session, settings: Settings, *, demo: bool, clock: Clock | None = None) -> str:
    seed_reference(session)
    ensure_roles(session)
    seed_inventory_reference(session)
    if not demo:
        return "Reference data is in place."
    users = seed_demo_users(session)
    ensure_roles(session)  # give the new demo accounts the base role
    today = (clock or Clock(settings.timezone)).today()
    n = seed_demo_requests(session, settings, users, today)
    items = seed_inventory_demo(session, settings, users, today, clock)
    return (
        f"Reference data, {len(users)} demo accounts, {n} demo requests"
        f"{' and demo inventory' if items else ''} are in place."
    )
