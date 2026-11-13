from __future__ import annotations

import base64
import io

from openpyxl import Workbook, load_workbook

PASSWORD = "Initial-Pass-2026"


def workbook(
    *rows: tuple[str, ...], header: tuple[str, ...] = ("Email", "Name", "Job title", "Team", "Roles")
) -> str:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Users"
    ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    out = io.BytesIO()
    wb.save(out)
    return base64.b64encode(out.getvalue()).decode()


def test_template_lists_columns_teams_and_roles(login) -> None:  # type: ignore[no-untyped-def]
    admin = login("admin@example.com")
    r = admin.get("/admin/users/import-template.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert [c.value for c in wb["Users"][1]] == ["Email", "Name", "Job title", "Team", "Roles"]
    teams = [c.value for c in wb["Lists"]["A"][1:] if c.value]
    assert "Development Team" in teams and "Support Team" in teams
    assert login("priya.nair@example.com").get("/admin/users/import-template.xlsx").status_code == 403


def test_preview_then_import_creates_and_updates_by_email(login) -> None:  # type: ignore[no-untyped-def]
    admin = login("admin@example.com")
    before = {u["email"]: u for u in admin.get("/admin/users").json()}
    priya = before["priya.nair@example.com"]
    file = workbook(
        ("New.Engineer@Example.com", "New Engineer", "Developer", "Development Team", ""),
        ("new.lead@example.com", "New Lead", "", "DEV", "Team leader"),
        ("priya.nair@example.com", "", "Principal Engineer", "", "Engineer"),
        ("alex.tan@example.com", "", "", "", ""),
        ("not-an-email", "Someone", "", "", ""),
        ("new.engineer@example.com", "Twice", "", "", ""),
        ("x@example.com", "X", "", "Nowhere", ""),
        ("y@example.com", "Y", "", "", "Boss"),
        ("z@example.com", "", "", "", ""),
    )

    preview = admin.post("/admin/users/import", json={"file_base64": file, "initial_password": PASSWORD})
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert (p["applied"], p["created"], p["updated"], p["unchanged"], p["errors"]) == (False, 2, 1, 1, 5)
    errors = {r["row"]: r["error"] for r in p["rows"] if r["outcome"] == "error"}
    assert errors == {
        6: '"not-an-email" is not a valid email address.',
        7: "This email address appears more than once in the file.",
        8: 'There is no team called "Nowhere".',
        9: '"boss" is not a role. Use: Requester, Engineer, Team leader, Director, Viewer, Administrator, Inventory editor, Operations manager.',
        10: "A name is needed to add a new person.",
    }
    assert len(admin.get("/admin/users").json()) == len(before), "a preview saves nothing"

    done = admin.post(
        "/admin/users/import", json={"file_base64": file, "initial_password": PASSWORD, "apply": True}
    )
    assert done.status_code == 200 and done.json()["applied"] is True
    after = {u["email"]: u for u in admin.get("/admin/users").json()}
    eng = after["new.engineer@example.com"]
    assert eng["display_name"] == "New Engineer" and eng["job_title"] == "Developer"
    assert eng["team"]["name"] == "Development Team"
    assert sorted(eng["roles"]) == ["ENGINEER", "REQUESTER"] and eng["must_change_password"] is True
    assert sorted(after["new.lead@example.com"]["roles"]) == ["REQUESTER", "TEAM_LEADER"]
    p2 = after["priya.nair@example.com"]
    assert p2["display_name"] == priya["display_name"], "a blank cell keeps the current value"
    assert p2["job_title"] == "Principal Engineer"
    assert set(p2["roles"]) == set(priya["roles"]) | {"ENGINEER"}, "roles are only ever added"

    new = login("new.engineer@example.com", PASSWORD)
    assert new.me["must_change_password"] is True

    again = admin.post("/admin/users/import", json={"file_base64": file, "initial_password": PASSWORD}).json()
    assert again["created"] == 0 and again["updated"] == 0


def test_import_rejects_weak_password_and_unreadable_files(login) -> None:  # type: ignore[no-untyped-def]
    admin = login("admin@example.com")
    file = workbook(("a@example.com", "A", "", "", ""))
    weak = admin.post("/admin/users/import", json={"file_base64": file, "initial_password": "short"})
    assert weak.status_code == 422 and "initial_password" in weak.json()["details"]["fields"]
    junk = base64.b64encode(b"not a spreadsheet").decode()
    bad = admin.post("/admin/users/import", json={"file_base64": junk, "initial_password": PASSWORD})
    assert bad.status_code == 422 and "could not be read" in bad.json()["message"]
    no_email = workbook(("A",), header=("Name",))
    r = admin.post("/admin/users/import", json={"file_base64": no_email, "initial_password": PASSWORD})
    assert r.status_code == 422 and "Email" in r.json()["message"]
