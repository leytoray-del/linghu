"""Create and update user accounts from an Excel sheet, matching people by email address.

Rules:

* A new email address creates an account with the given initial password, which the person must
  change when they first sign in. Without roles in the sheet it gets Requester and Engineer.
* An existing email address updates the name, job title and team where the sheet has a value.
  Roles in the sheet are added to the person's current roles; roles are never removed by an import,
  so approvers and administrators cannot lose their access by accident.
* Rows with problems are reported and skipped. Nothing is saved unless ``apply`` is true.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import EmailStr, TypeAdapter, ValidationError

from erf.core.errors import ValidationFailed
from erf.core.security import hash_password, password_problems
from erf.db.models import Team, User
from erf.domain.enums import Role
from erf.repositories.users import TeamRepository, UserRepository
from erf.schemas.admin import UserImportOut, UserImportRow
from erf.services.context import ServiceContext

MAX_ROWS = 2000
DEFAULT_ROLES = {Role.REQUESTER, Role.ENGINEER}
HEADERS = ["Email", "Name", "Job title", "Team", "Roles"]
ROLE_NAMES: dict[Role, str] = {
    Role.REQUESTER: "Requester",
    Role.ENGINEER: "Engineer",
    Role.TEAM_LEADER: "Team leader",
    Role.DIRECTOR: "Director",
    Role.VIEWER: "Viewer",
    Role.ADMIN: "Administrator",
}
_ROLE_WORDS = {name.lower(): role for role, name in ROLE_NAMES.items()} | {
    "admin": Role.ADMIN,
    "tl": Role.TEAM_LEADER,
    "teamleader": Role.TEAM_LEADER,
    "team_leader": Role.TEAM_LEADER,
}
_HEADER_KEYS = {
    "email": "email",
    "email address": "email",
    "name": "name",
    "display name": "name",
    "job title": "job_title",
    "title": "job_title",
    "team": "team",
    "role": "roles",
    "roles": "roles",
}
_EMAIL = TypeAdapter(EmailStr)


@dataclass
class _Row:
    number: int
    values: dict[str, str] = field(default_factory=dict)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


class UserImportService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session
        self.users = UserRepository(self.s)

    # ---- template -------------------------------------------------------------------------

    def template_xlsx(self) -> bytes:
        teams = [t for t in TeamRepository(self.s).list_all() if t.is_active]
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Users"
        ws.append(HEADERS)
        head_fill = PatternFill("solid", fgColor="1F3A5F")
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
        for col, width in zip("ABCDE", (34, 26, 28, 26, 30), strict=True):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"

        lists = wb.create_sheet("Lists")
        lists.append(["Teams", "", "Roles"])
        for cell in lists[1]:
            cell.font = Font(bold=True)
        for i, name in enumerate([t.name for t in teams] or [""], start=2):
            lists.cell(row=i, column=1, value=name)
        for i, name in enumerate(ROLE_NAMES.values(), start=2):
            lists.cell(row=i, column=3, value=name)
        lists.column_dimensions["A"].width = 30
        lists.column_dimensions["C"].width = 18
        if teams:
            choose_team = DataValidation(
                type="list", formula1=f"=Lists!$A$2:$A${len(teams) + 1}", allow_blank=True
            )
            choose_team.error = "Choose a team from the list."
            ws.add_data_validation(choose_team)
            choose_team.add(f"D2:D{MAX_ROWS + 1}")

        guide = wb.create_sheet("How to fill in")
        guide.column_dimensions["A"].width = 110
        lines = [
            "How to fill in the Users sheet",
            "",
            "Email: required. People are matched by email address, so an existing person is updated, not added twice.",
            "Name: required for new people. For existing people, leave it blank to keep the current name.",
            "Job title: optional. Leave it blank to keep the current job title.",
            "Team: optional. Choose from the list. Leave it blank to keep the current team.",
            "Roles: optional. Separate several roles with commas, for example: Engineer, Team leader.",
            "   New people with no roles get Requester and Engineer.",
            "   For existing people, the roles are added to the ones they already have. "
            "Remove roles on the Users page.",
            "   Roles: " + ", ".join(ROLE_NAMES.values()) + ".",
            "",
            "New people sign in with the initial password you enter when you import the file, "
            "and must choose their own password the first time.",
        ]
        for i, line in enumerate(lines, start=1):
            cell = guide.cell(row=i, column=1, value=line)
            cell.alignment = Alignment(wrap_text=True)
        guide["A1"].font = Font(bold=True, size=13)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    # ---- import ---------------------------------------------------------------------------

    def _read(self, content: bytes) -> list[_Row]:
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
            raise ValidationFailed(
                "This file could not be read. Save it as an Excel workbook (.xlsx) and try again."
            ) from exc
        ws = wb["Users"] if "Users" in wb.sheetnames else wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        columns: dict[int, str] = {}
        for i, value in enumerate(header or ()):
            key = _HEADER_KEYS.get(_text(value).lower())
            if key and key not in columns.values():
                columns[i] = key
        if "email" not in columns.values():
            raise ValidationFailed(
                "The first row must contain the column headings, including Email. "
                "Download the template to see the expected layout."
            )
        result: list[_Row] = []
        for number, values in enumerate(rows, start=2):
            row = _Row(number, {key: _text(values[i]) for i, key in columns.items() if i < len(values)})
            if any(row.values.values()):
                result.append(row)
        wb.close()
        if len(result) > MAX_ROWS:
            raise ValidationFailed(f"The file has {len(result)} people. Import at most {MAX_ROWS} at a time.")
        if not result:
            raise ValidationFailed("The file has no people to import.")
        return result

    @staticmethod
    def _roles(text: str) -> set[Role]:
        roles: set[Role] = set()
        for word in text.replace(";", ",").split(","):
            word = word.strip().lower()
            if not word:
                continue
            role = _ROLE_WORDS.get(word)
            if role is None:
                raise ValueError(f'"{word}" is not a role. Use: ' + ", ".join(ROLE_NAMES.values()) + ".")
            roles.add(role)
        return roles

    def run(self, content: bytes, initial_password: str, *, apply: bool) -> UserImportOut:
        problems = password_problems(initial_password)
        if problems:
            raise ValidationFailed(
                "Choose a stronger initial password. " + " ".join(problems),
                details={"fields": {"initial_password": " ".join(problems)}},
            )
        teams: dict[str, Team] = {}
        for t in TeamRepository(self.s).list_all():
            if t.is_active:
                teams[t.name.strip().lower()] = t
                teams[t.code.strip().lower()] = t
        password_hash: str | None = None
        seen: set[str] = set()
        out: list[UserImportRow] = []

        for row in self._read(content):
            v = row.values
            email, name = v.get("email", "").lower(), v.get("name", "")
            result = UserImportRow(row=row.number, email=email, name=name, outcome="error", changes=[])
            out.append(result)
            try:
                if not email:
                    raise ValueError("The email address is missing.")
                try:
                    _EMAIL.validate_python(email)
                except ValidationError:
                    raise ValueError(f'"{email}" is not a valid email address.') from None
                if email in seen:
                    raise ValueError("This email address appears more than once in the file.")
                seen.add(email)
                team: Team | None = None
                if v.get("team"):
                    team = teams.get(v["team"].lower())
                    if team is None:
                        raise ValueError(f'There is no team called "{v["team"]}".')
                roles = self._roles(v.get("roles", ""))
                for key, limit, label in (("name", 120, "name"), ("job_title", 120, "job title")):
                    if len(v.get(key, "")) > limit:
                        raise ValueError(f"The {label} is longer than {limit} characters.")
            except ValueError as exc:
                result.error = str(exc)
                continue

            user = self.users.get_by_email(email)
            if user is None:
                if not name:
                    result.error = "A name is needed to add a new person."
                    continue
                result.outcome = "create"
                new_roles = (roles or DEFAULT_ROLES) | {Role.REQUESTER}
                result.changes = [
                    "New account",
                    "Roles: " + ", ".join(ROLE_NAMES[r] for r in ROLE_NAMES if r in new_roles),
                ]
                if team:
                    result.changes.append(f"Team: {team.name}")
                if apply:
                    password_hash = password_hash or hash_password(initial_password)
                    user = User(
                        email=email,
                        display_name=name,
                        job_title=v.get("job_title") or None,
                        team_id=team.id if team else None,
                        password_hash=password_hash,
                        must_change_password=True,
                        is_active=True,
                    )
                    user.set_roles(new_roles)
                    self.users.add(user)
                continue

            result.name = name or user.display_name
            changes: list[str] = []
            if name and name != user.display_name:
                changes.append(f"Name: {user.display_name} → {name}")
            if v.get("job_title") and v["job_title"] != (user.job_title or ""):
                changes.append(f"Job title: {user.job_title or '(none)'} → {v['job_title']}")
            if team and team.id != user.team_id:
                changes.append(f"Team: {user.team.name if user.team else '(none)'} → {team.name}")
            added = roles - set(user.roles)
            if added:
                changes.append("Roles added: " + ", ".join(ROLE_NAMES[r] for r in ROLE_NAMES if r in added))
            if not user.is_active:
                changes.append("Note: this account is deactivated and stays deactivated")
            real_changes = [c for c in changes if not c.startswith("Note:")]
            result.outcome = "update" if real_changes else "unchanged"
            result.changes = changes
            if apply and real_changes:
                if name:
                    user.display_name = name
                if v.get("job_title"):
                    user.job_title = v["job_title"]
                if team:
                    user.team_id = team.id
                if added:
                    user.set_roles(set(user.roles) | added)
        if apply:
            self.s.flush()
        count = {k: sum(1 for r in out if r.outcome == k) for k in ("create", "update", "unchanged", "error")}
        return UserImportOut(
            applied=apply,
            created=count["create"],
            updated=count["update"],
            unchanged=count["unchanged"],
            errors=count["error"],
            rows=out,
        )
