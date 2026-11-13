from __future__ import annotations

import io
from typing import Any

from openpyxl import load_workbook

CLERK = "muthu.selvam@example.com"
ENGINEER = "jason.teo@example.com"
ADMIN = "admin@example.com"


def lookups(session) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    data = session.get("/inventory/lookups").json()
    return {
        "projects": {p["name"]: p["id"] for p in data["projects"]},
        "locations": {loc["name"]: loc["id"] for loc in data["locations"]},
        "models": {m["model_no"]: m["id"] for m in data["models"]},
        "categories": {c["code"]: c for c in data["categories"]},
    }


def delivery(
    lk: dict[str, Any], *items: dict[str, Any], project: str = "HSA Permit Portal"
) -> dict[str, Any]:
    return {
        "project_id": lk["projects"][project],
        "received_on": "2026-11-04",
        "location_id": lk["locations"]["NEC Store, Level 3"],
        "delivery_order_no": "DO-90001",
        "items": list(items),
    }


def reader(serial: str, lk: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "serial_no": serial,
        "model_id": lk["models"]["FRX-200"],
        "warranty_start": "2026-11-01",
        "warranty_end": "2029-10-31",
        **extra,
    }


def test_permissions_by_role(login) -> None:  # type: ignore[no-untyped-def]
    clerk, engineer, admin = login(CLERK), login(ENGINEER), login(ADMIN)
    assert "inventory.register" in clerk.me["permissions"]
    assert engineer.me["permissions"] == [
        "inventory.register",
        "inventory.return",
        "inventory.view",
        "inventory.withdraw",
    ]
    assert "inventory.edit" in clerk.me["permissions"] and "inventory.edit" not in engineer.me["permissions"]
    assert {"core.admin", "inventory.admin"} <= set(admin.me["permissions"])
    lk = lookups(engineer)
    assert engineer.get("/inventory/items").status_code == 200
    r = engineer.post("/inventory/deliveries", json=delivery(lk, reader("FRX26A0001", lk)))
    assert r.status_code == 201, "engineers register devices when they arrive"
    item = engineer.get(
        f"/inventory/items/{r.json()['id'] and engineer.get('/inventory/items/check-serial', params={'serial': 'FRX26A0001'}).json()['item_id']}"
    ).json()
    edit = engineer.put(
        f"/inventory/items/{item['id']}",
        json={
            "version": item["version"],
            "attributes": {},
            "warranty_start": item["warranty_start"],
            "warranty_end": item["warranty_end"],
        },
    )
    assert edit.status_code == 403, "changing a saved item is a separate permission"
    gone = engineer.post(
        f"/inventory/items/{item['id']}/delete", json={"version": item["version"], "reason": "x"}
    )
    assert gone.status_code == 403, "deleting is a separate permission"
    viewer = login("pmo@example.com")
    assert (
        viewer.post("/inventory/deliveries", json=delivery(lk, reader("FRX26A0002", lk))).status_code == 403
    )
    assert clerk.post("/inventory/categories", json={"code": "X", "name": "X"}).status_code == 403
    cat_id = lk["categories"]["FR_READER"]["id"]
    new_model = clerk.post(
        "/inventory/models",
        json={"category_id": cat_id, "model_no": "FRX-300", "serial_pattern": "FRX3[0-9]{6}"},
    )
    assert new_model.status_code == 201, "clerks can add a model while registering"
    assert (
        clerk.put(
            f"/inventory/models/{new_model.json()['id']}", json={"category_id": cat_id, "model_no": "FRX-301"}
        ).status_code
        == 403
    )
    assert (
        login("pmo@example.com")
        .post("/inventory/models", json={"category_id": cat_id, "model_no": "FRX-400"})
        .status_code
        == 403
    )
    assert clerk.post("/projects", json={"code": "P1", "name": "P"}).status_code == 403


def test_clerk_registers_a_delivery_under_a_project(login) -> None:  # type: ignore[no-untyped-def]
    clerk = login(CLERK)
    lk = lookups(clerk)
    before = clerk.get(
        "/inventory/summary", params={"project_id": lk["projects"]["HSA Permit Portal"]}
    ).json()
    r = clerk.post(
        "/inventory/deliveries",
        json=delivery(
            lk,
            reader(" frx26a 0001 ", lk, attributes={"fr_id": "FR-9001", "mounting_type": "wall"}),
            reader("FRX26A0002", lk),
        ),
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["delivery_no"].startswith("GRN-2026-") and d["item_count"] == 2
    check = clerk.get("/inventory/items/check-serial", params={"serial": "frx26a0001"}).json()
    assert check["exists"] is True and "HSA Permit Portal" in check["message"]
    item = clerk.get(f"/inventory/items/{check['item_id']}").json()
    assert item["serial_no"] == "FRX26A0001" and item["status"] == "IN_STOCK"
    assert item["attributes"] == {"fr_id": "FR-9001", "mounting_type": "Wall"}
    assert (
        item["history"][0]["kind"] == "RECEIVE" and item["history"][0]["to_location"] == "NEC Store, Level 3"
    )
    after = clerk.get("/inventory/summary", params={"project_id": lk["projects"]["HSA Permit Portal"]}).json()
    assert after["counts"]["in_stock"] == before["counts"]["in_stock"] + 2


def test_delivery_problems_are_reported_per_item(login) -> None:  # type: ignore[no-untyped-def]
    clerk = login(CLERK)
    lk = lookups(clerk)
    r = clerk.post(
        "/inventory/deliveries",
        json=delivery(
            lk,
            reader("FRX24A0193", lk),  # already registered by the demo data
            reader("FRX26A0100", lk),
            reader("FRX26A0100", lk),  # twice in the same delivery
            reader("NOTAREADER", lk),  # does not match the model's serial format
            reader("FRX26A0101", lk, warranty_end=None),
            reader("FRX26A0102", lk, attributes={"mounting_type": "Ceiling", "colour": "red"}),
        ),
    )
    assert r.status_code == 422
    body = r.json()
    fields = body["details"]["fields"]
    assert body["message"] == "5 items need attention before the delivery can be saved."
    assert "already registered under HSA Permit Portal" in fields["items.0.serial_no"]
    assert "more than once" in fields["items.2.serial_no"]
    assert "does not look like a FRX-200 serial number" in fields["items.3.serial_no"]
    assert fields["items.4.warranty_end"] == "The warranty end date is required for this category."
    assert fields["items.5.attributes.mounting_type"].startswith("Choose one of: Wall")
    assert fields["items.5.attributes.colour"] == "This field does not belong to the category."
    assert (
        clerk.get("/inventory/items/check-serial", params={"serial": "FRX26A0100"}).json()["exists"] is False
    )


def test_editing_an_item_is_recorded_and_checks_the_version(login) -> None:  # type: ignore[no-untyped-def]
    clerk = login(CLERK)
    item_id = clerk.get("/inventory/items/check-serial", params={"serial": "FRX24A0195"}).json()["item_id"]
    item = clerk.get(f"/inventory/items/{item_id}").json()
    body = {
        "version": item["version"],
        "warranty_start": item["warranty_start"],
        "warranty_end": item["warranty_end"],
        "attributes": {**item["attributes"], "fr_id": "FR-0195", "apk_version": "2.9.0"},
        "remarks": None,
    }
    r = clerk.put(f"/inventory/items/{item_id}", json=body)
    assert r.status_code == 200, r.text
    updated = r.json()
    change = updated["history"][0]
    assert change["kind"] == "UPDATE" and change["actor"]["display_name"] == "Muthu Selvam"
    assert change["changes"] == {
        "APK version": {"from": "2.8.0", "to": "2.9.0"},
        "FR ID": {"from": None, "to": "FR-0195"},
    }
    stale = clerk.put(f"/inventory/items/{item_id}", json=body)
    assert stale.status_code == 409


def test_delete_and_return_need_their_own_permissions(login) -> None:  # type: ignore[no-untyped-def]
    admin, engineer, editor = login(ADMIN), login(ENGINEER), login(CLERK)
    lk = lookups(admin)
    item_id = admin.get("/inventory/items/check-serial", params={"serial": "FRX24A0196"}).json()["item_id"]
    item = admin.get(f"/inventory/items/{item_id}").json()
    assert (
        editor.post(
            f"/inventory/items/{item_id}/delete", json={"version": item["version"], "reason": "x"}
        ).status_code
        == 403
    )
    r = admin.post(
        f"/inventory/items/{item_id}/delete",
        json={"version": item["version"], "reason": "Registered twice by mistake."},
    )
    assert r.status_code == 200 and r.json()["deleted_at"] and r.json()["history"][0]["kind"] == "DELETE"
    listed = admin.get("/inventory/items", params={"q": "FRX24A0196"}).json()
    assert listed["total"] == 0, "deleted items leave the lists"
    assert (
        "deleted"
        in admin.get("/inventory/items/check-serial", params={"serial": "FRX24A0196"}).json()["message"]
    )

    # Return to stock: only deployed items, only to a store, by people allowed to return.
    deployed = admin.get("/inventory/items/check-serial", params={"serial": "FRX24A0194"}).json()["item_id"]
    item = engineer.get(f"/inventory/items/{deployed}").json()
    assert item["status"] == "DEPLOYED" and item["location"]["name"] == "HSA Outram, Gate 2"
    bad = engineer.post(
        f"/inventory/items/{deployed}/return",
        json={"version": item["version"], "location_id": lk["locations"]["HSA Outram, Gate 2"]},
    )
    assert bad.status_code == 422
    assert (
        login("pmo@example.com")
        .post(f"/inventory/items/{deployed}/return", json={"version": item["version"], "location_id": 1})
        .status_code
        == 403
    )
    back = engineer.post(
        f"/inventory/items/{deployed}/return",
        json={
            "version": item["version"],
            "location_id": lk["locations"]["NEC Store, Level 3"],
            "reason": "Pilot ended.",
        },
    )
    assert back.status_code == 200, back.text
    assert back.json()["status"] == "IN_STOCK" and back.json()["history"][0]["kind"] == "RETURN"


def test_categories_are_configurable_without_losing_fields(login) -> None:  # type: ignore[no-untyped-def]
    admin = login(ADMIN)
    r = admin.post(
        "/inventory/categories",
        json={
            "code": "BARRIER",
            "name": "Barrier gate",
            "warranty_required": False,
            "fields": [
                {"key": "arm_length", "label": "Arm length (m)", "type": "number", "show_in_list": True},
                {"key": "side", "label": "Side", "type": "choice", "choices": ["Left", "Right"]},
            ],
        },
    )
    assert r.status_code == 201, r.text
    cat = r.json()
    model = admin.post("/inventory/models", json={"category_id": cat["id"], "model_no": "BG-300"}).json()
    base = {"code": "BARRIER", "name": "Barrier gate", "warranty_required": False}
    changed_type = admin.put(
        f"/inventory/categories/{cat['id']}",
        json={**base, "fields": [{"key": "arm_length", "label": "Arm", "type": "text"}, cat["fields"][1]]},
    )
    assert changed_type.status_code == 422
    assert "cannot change" in changed_type.json()["details"]["fields"]["fields.0.type"]
    removed = admin.put(f"/inventory/categories/{cat['id']}", json={**base, "fields": [cat["fields"][0]]})
    assert removed.status_code == 422 and "Retire them instead" in removed.json()["message"]
    retired = admin.put(
        f"/inventory/categories/{cat['id']}",
        json={**base, "fields": [cat["fields"][0], {**cat["fields"][1], "retired": True}]},
    )
    assert retired.status_code == 200
    lk = lookups(admin)
    r = admin.post(
        "/inventory/deliveries",
        json=delivery(
            lk, {"serial_no": "BG0001", "model_id": model["id"], "attributes": {"arm_length": "4.5"}}
        ),
    )
    assert r.status_code == 201, r.text
    item_id = admin.get("/inventory/items/check-serial", params={"serial": "BG0001"}).json()["item_id"]
    assert admin.get(f"/inventory/items/{item_id}").json()["attributes"] == {"arm_length": 4.5}


def test_inventory_list_summary_and_export(login) -> None:  # type: ignore[no-untyped-def]
    eng = login(ENGINEER)
    lk = lookups(eng)
    hsa = lk["projects"]["HSA Permit Portal"]
    summary = eng.get("/inventory/summary", params={"project_id": hsa}).json()
    assert summary["counts"] == {"in_stock": 18, "requested": 1, "deployed": 2, "total": 21}
    assert eng.get("/inventory/summary").json()["warranty_ending"] == 6
    page = eng.get("/inventory/items", params={"project_id": hsa, "q": "turnstile"}).json()
    assert page["total"] == 4
    at_site = eng.get(
        "/inventory/items", params={"location_id": lk["locations"]["HSA Outram, Gate 2"]}
    ).json()
    assert sorted(i["serial_no"] for i in at_site["items"]) == ["FRX24A0194", "FRX24A0195"]
    soon = eng.get("/inventory/items", params={"warranty_within_days": 60}).json()
    assert soon["total"] == 6 and soon["items"][0]["project"]["name"] == "MOM Kiosk Refresh"
    xlsx = eng.get("/inventory/export.xlsx", params={"project_id": hsa})
    assert xlsx.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert wb.sheetnames == ["Camera", "FR reader", "Gateway", "Tablet"]
    assert [c.value for c in wb["FR reader"][1]][:7] == [
        "Serial no.", "Model", "Project", "Status", "Location", "Warranty start", "Warranty end",
    ]  # fmt: skip


def test_withdrawal_needs_pm_then_om_and_moves_the_items(login, container) -> None:  # type: ignore[no-untyped-def]
    eng, pm, om, admin = (
        login(ENGINEER),
        login("alex.tan@example.com"),
        login("wong.meifen@example.com"),
        login(ADMIN),
    )
    lk = lookups(eng)
    hsa = lk["projects"]["HSA Permit Portal"]
    ids = [
        eng.get("/inventory/items/check-serial", params={"serial": s}).json()["item_id"]
        for s in ("FRX24A0197", "FRX24A0198")
    ]
    site = eng.post("/inventory/sites", json={"name": "HSA  Novena,   Lobby"})
    assert (
        site.status_code == 201
        and site.json()["name"] == "HSA Novena, Lobby"
        and site.json()["kind"] == "SITE"
    )
    assert eng.post("/inventory/sites", json={"name": "hsa novena, lobby"}).json()["id"] == site.json()["id"]
    body = {
        "project_id": hsa,
        "item_ids": ids,
        "to_location_id": site.json()["id"],
        "reason": "Lobby readers.",
    }

    other = lk["projects"]["MOM Kiosk Refresh"]
    wrong = eng.post("/inventory/withdrawals", json={**body, "project_id": other})
    assert wrong.status_code == 422 and "belongs to HSA Permit Portal" in wrong.json()["message"]
    w = eng.post("/inventory/withdrawals", json=body)
    assert w.status_code == 201, w.text
    w = w.json()
    assert w["status"] == "PENDING_PM" and [u["display_name"] for u in w["waiting_for"]] == ["Alex Tan"]
    assert eng.get(f"/inventory/items/{ids[0]}").json()["status"] == "REQUESTED"
    again = eng.post("/inventory/withdrawals", json=body)
    assert again.status_code == 422 and "not in stock" in again.json()["message"]
    assert pm.get("/auth/me").json()["withdrawal_task_count"] == 2  # this one and the one from the demo data
    assert (
        om.post(
            f"/inventory/withdrawals/{w['id']}/decision", json={"version": w["version"], "approve": True}
        ).status_code
        == 403
    )

    # Reject: back to the requester; the items return to stock.
    no = pm.post(
        f"/inventory/withdrawals/{w['id']}/decision", json={"version": w["version"], "approve": False}
    )
    assert no.status_code == 422
    w = pm.post(
        f"/inventory/withdrawals/{w['id']}/decision",
        json={"version": w["version"], "approve": False, "comment": "Take three."},
    ).json()
    assert w["status"] == "RETURNED" and w["can_decide"] is False
    assert eng.get(f"/inventory/items/{ids[0]}").json()["status"] == "IN_STOCK"
    detail = eng.get(f"/inventory/withdrawals/{w['id']}").json()
    assert detail["can_revise"] and detail["can_withdraw"]

    third = eng.get("/inventory/items/check-serial", params={"serial": "FRX24A0199"}).json()["item_id"]
    w = eng.put(
        f"/inventory/withdrawals/{w['id']}",
        json={**body, "item_ids": [*ids, third], "version": detail["version"]},
    ).json()
    assert w["status"] == "PENDING_PM" and w["item_count"] == 3
    w = pm.post(
        f"/inventory/withdrawals/{w['id']}/decision", json={"version": w["version"], "approve": True}
    ).json()
    assert w["status"] == "PENDING_OM" and [u["display_name"] for u in w["waiting_for"]] == ["Wong Mei Fen"]
    w = om.post(
        f"/inventory/withdrawals/{w['id']}/decision", json={"version": w["version"], "approve": True}
    ).json()
    assert w["status"] == "APPROVED"
    item = eng.get(f"/inventory/items/{ids[0]}").json()
    assert item["status"] == "DEPLOYED" and item["location"]["name"] == "HSA Novena, Lobby"
    assert item["attributes"]["deployment_date"] == "2026-11-05", (
        "the deployment date is filled in on approval"
    )
    assert item["history"][0]["kind"] == "DEPLOY" and item["history"][0]["withdrawal_no"] == w["request_no"]

    from sqlalchemy import select

    from erf.db.models import NotificationOutbox
    from erf.db.session import session_scope

    with session_scope(container.factory) as s:
        events = [
            r.event_type
            for r in s.scalars(
                select(NotificationOutbox)
                .where(NotificationOutbox.event_type.like("WITHDRAWAL%"))
                .order_by(NotificationOutbox.id)
            )
        ]
    assert events[-5:] == [
        "WITHDRAWAL_WAITING",
        "WITHDRAWAL_REJECTED",
        "WITHDRAWAL_WAITING",
        "WITHDRAWAL_WAITING",
        "WITHDRAWAL_APPROVED",
    ]

    # When the requester is the project's PM, the PM step is skipped; withdrawing releases the items.
    users = {u["email"]: u["id"] for u in admin.get("/admin/users").json()}
    project = next(p for p in admin.get("/projects").json() if p["id"] == hsa)
    admin.put(
        f"/projects/{hsa}",
        json={
            "code": project["code"],
            "name": project["name"],
            "client_name": project["client_name"],
            "pm_user_id": users[ENGINEER],
            "is_active": True,
        },
    )
    four = eng.get("/inventory/items/check-serial", params={"serial": "FRX24A0200"}).json()["item_id"]
    w2 = eng.post("/inventory/withdrawals", json={**body, "item_ids": [four]}).json()
    assert w2["status"] == "PENDING_OM" and w2["tasks"][0]["status"] == "SKIPPED"
    w2 = eng.post(f"/inventory/withdrawals/{w2['id']}/withdraw", json={"version": w2["version"]}).json()
    assert w2["status"] == "WITHDRAWN" and eng.get(f"/inventory/items/{four}").json()["status"] == "IN_STOCK"
    assert login("pmo@example.com").post("/inventory/withdrawals", json=body).status_code == 403


def test_projects_and_locations_are_shared_records(login) -> None:  # type: ignore[no-untyped-def]
    admin = login(ADMIN)
    users = {u["email"]: u["id"] for u in admin.get("/admin/users").json()}
    r = admin.post(
        "/projects",
        json={"code": "p26-0999", "name": "NLB Branch Upgrade", "pm_user_id": users["alex.tan@example.com"]},
    )
    assert (
        r.status_code == 201
        and r.json()["code"] == "P26-0999"
        and r.json()["pm"]["display_name"] == "Alex Tan"
    )
    dup = admin.post("/projects", json={"code": "P26-0999", "name": "Other"})
    assert dup.status_code == 409
    r = admin.post("/locations", json={"name": "nec store, level 3", "kind": "STORE"})
    assert r.status_code == 409
    assert login(ENGINEER).get("/projects").status_code == 200
