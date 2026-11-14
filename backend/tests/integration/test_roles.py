from __future__ import annotations

from typing import Any

ADMIN = "admin@example.com"
ENGINEER = "jason.teo@example.com"


def user_body(u: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    return {
        "display_name": u["display_name"],
        "job_title": u["job_title"],
        "team_id": u["team"]["id"] if u["team"] else None,
        "skills": u["skills"],
        "roles": roles,
        "is_active": u["is_active"],
    }


def test_roles_screen_lists_roles_and_the_catalogue(login) -> None:  # type: ignore[no-untyped-def]
    admin = login(ADMIN)
    data = admin.get("/admin/roles").json()
    roles = {r["code"]: r for r in data["roles"]}
    assert [r["name"] for r in data["roles"]][:3] == ["Everyone", "Engineer", "Team leader"]
    duties = {p["key"] for p in data["permissions"] if p["duty"]}
    assert duties == {"resources.review", "resources.approve", "resources.assignable", "inventory.approve"}
    assert roles["ADMIN"]["is_locked"] and set(roles["ADMIN"]["permissions"]) == {
        p["key"] for p in data["permissions"] if not p["duty"]
    }, "Administrator has everything except responsibilities"
    assert roles["REQUESTER"]["permissions"] == ["inventory.view", "resources.request"]
    assert roles["ENGINEER"]["permissions"] == [
        "inventory.register",
        "inventory.return",
        "inventory.withdraw",
        "resources.assignable",
    ]
    assert "resources.approve" in roles["DIRECTOR"]["permissions"]
    assert roles["REQUESTER"]["is_base"] and roles["REQUESTER"]["user_count"] >= 17
    assert {p["module_name"] for p in data["permissions"]} == {"Platform", "Resources", "Inventory"}
    assert login(ENGINEER).get("/admin/roles").status_code == 403


def test_permissions_follow_the_roles_screen(login, container) -> None:  # type: ignore[no-untyped-def]
    admin = login(ADMIN)
    roles = {r["code"]: r for r in admin.get("/admin/roles").json()["roles"]}
    engineer_perms = roles["ENGINEER"]["permissions"]

    # Taking a permission away from a system role takes it away from everyone holding only that role.
    body = {
        "name": "Engineer",
        "description": roles["ENGINEER"]["description"],
        "permissions": [p for p in engineer_perms if p != "inventory.register"],
    }
    assert admin.put("/admin/roles/ENGINEER", json=body).status_code == 200
    eng = login(ENGINEER)
    assert "inventory.register" not in eng.me["permissions"]
    lookups = eng.get("/inventory/lookups").json()
    delivery = {
        "project_id": lookups["projects"][0]["id"], "received_on": "2026-11-04", "location_id": lookups["locations"][0]["id"],
        "items": [{"serial_no": "ZZ0001", "model_id": lookups["models"][0]["id"], "warranty_start": "2026-11-01", "warranty_end": "2027-11-01"}],
    }  # fmt: skip
    assert eng.post("/inventory/deliveries", json=delivery).status_code == 403

    # The defaults are applied once: starting again does not give the permission back.
    from erf.db.session import session_scope
    from erf.services.role_service import ensure_roles

    with session_scope(container.factory) as s:
        ensure_roles(s)
    assert "inventory.register" not in login(ENGINEER).me["permissions"]

    # A custom role adds a permission to the people who hold it.
    r = admin.post(
        "/admin/roles",
        json={
            "name": "Store keeper",
            "description": "Keeps the store.",
            "permissions": ["inventory.view", "inventory.edit", "inventory.register"],
        },
    )
    assert r.status_code == 201, r.text
    keeper = r.json()
    assert keeper["code"] == "STORE_KEEPER" and not keeper["is_system"]
    users = {u["email"]: u for u in admin.get("/admin/users").json()}
    jason = users[ENGINEER]
    assert (
        admin.put(
            f"/admin/users/{jason['id']}", json=user_body(jason, ["ENGINEER", "STORE_KEEPER"])
        ).status_code
        == 200
    )
    eng = login(ENGINEER)
    assert {"inventory.edit", "inventory.register"} <= set(eng.me["permissions"])
    assert "STORE_KEEPER" in eng.me["roles"] and "REQUESTER" in eng.me["roles"], (
        "everyone keeps the base role"
    )

    # Safeguards.
    assert (
        admin.put("/admin/roles/ADMIN", json={"name": "Administrator", "permissions": []}).status_code == 422
    )
    assert admin.delete("/admin/roles/ENGINEER").status_code == 422
    in_use = admin.delete("/admin/roles/STORE_KEEPER")
    assert in_use.status_code == 422 and "1 active user has this role" in in_use.json()["message"]
    dup = admin.post("/admin/roles", json={"name": "store keeper", "permissions": []})
    assert dup.status_code == 409
    bad = admin.put(f"/admin/users/{jason['id']}", json=user_body(jason, ["NO_SUCH_ROLE"]))
    assert bad.status_code == 422 and "do not exist" in bad.json()["message"]
    assert admin.put(f"/admin/users/{jason['id']}", json=user_body(jason, ["ENGINEER"])).status_code == 200
    assert admin.delete("/admin/roles/STORE_KEEPER").status_code == 204


def test_at_least_one_administrator_remains(login) -> None:  # type: ignore[no-untyped-def]
    admin = login(ADMIN)
    users = {u["email"]: u for u in admin.get("/admin/users").json()}
    me, other = users[ADMIN], users["grace.wong@example.com"]
    assert admin.put(f"/admin/users/{me['id']}", json=user_body(me, [])).status_code == 422
    assert (
        admin.put(f"/admin/users/{other['id']}", json=user_body(other, ["DIRECTOR", "ADMIN"])).status_code
        == 200
    )
    second = login("grace.wong@example.com")
    assert second.put(f"/admin/users/{me['id']}", json=user_body(me, [])).status_code == 200, (
        "another administrator remains"
    )
    assert "core.admin" not in login(ADMIN).me["permissions"]


def test_responsibilities_and_menus_follow_permissions(login) -> None:  # type: ignore[no-untyped-def]
    admin = login(ADMIN)
    roles = {r["code"]: r for r in admin.get("/admin/roles").json()["roles"]}
    # Administrator is not a final approver unless a role gives it that responsibility.
    assert "resources.approve" not in admin.me["permissions"]

    # Without "Raise resource requests", a person cannot raise one.
    everyone = roles["REQUESTER"]
    body = {"name": "Everyone", "description": everyone["description"], "permissions": ["inventory.view"]}
    assert admin.put("/admin/roles/REQUESTER", json=body).status_code == 200
    eng = login(ENGINEER)
    assert "resources.request" not in eng.me["permissions"]
    assert eng.post("/requests", json={}).status_code == 403
    assert "assigned" in eng.me["scopes"], "assignable engineers still see their work"
    body["permissions"] = everyone["permissions"]
    assert admin.put("/admin/roles/REQUESTER", json=body).status_code == 200


def test_replaced_permission_carries_over(container) -> None:  # type: ignore[no-untyped-def]
    """An installation from before the split keeps who could see everything."""
    from sqlalchemy import delete, select

    from erf.db.models import KnownPermission, RolePermission
    from erf.db.session import session_scope
    from erf.services.role_service import ensure_roles

    new = ["resources.view_all", "resources.load", "resources.reports"]
    with session_scope(container.factory) as s:
        s.execute(delete(RolePermission).where(RolePermission.permission.in_(new)))
        s.execute(delete(KnownPermission).where(KnownPermission.permission.in_(new)))
        s.add(KnownPermission(permission="resources.overview"))
        s.add(RolePermission(role_code="VIEWER", permission="resources.overview"))  # Director's was removed
    with session_scope(container.factory) as s:
        ensure_roles(s)
    with session_scope(container.factory) as s:
        grants = {(g.role_code, g.permission) for g in s.scalars(select(RolePermission))}
    assert {("VIEWER", p) for p in new} <= grants
    assert not any(r == "DIRECTOR" and p in new for r, p in grants)
    assert {("TEAM_LEADER", "resources.load"), ("TEAM_LEADER", "resources.reports")} <= grants
    assert not any(p == "resources.overview" for _, p in grants)
