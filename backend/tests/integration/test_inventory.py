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
    assert engineer.me["permissions"] == ["inventory.register", "inventory.view"]
    assert "inventory.edit" in clerk.me["permissions"] and "inventory.edit" not in engineer.me["permissions"]
    assert {"core.admin", "inventory.admin"} <= set(admin.me["permissions"])
    lk = lookups(engineer)
    assert engineer.get("/inventory/projects").status_code == 200
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
    move = engineer.post(
        f"/inventory/items/{item['id']}/actions/report_fault",
        json={"version": item["version"], "reason": "x"},
    )
    assert move.status_code == 403
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
    before = clerk.get(f"/inventory/projects/{lk['projects']['HSA Permit Portal']}").json()
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
    assert item["history"][0]["kind"] == "RECEIVE" and item["history"][0]["delivery_no"] == d["delivery_no"]
    after = clerk.get(f"/inventory/projects/{lk['projects']['HSA Permit Portal']}").json()
    assert after["totals"]["in_stock"] == before["totals"]["in_stock"] + 2


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


def test_item_actions_follow_the_lifecycle(login) -> None:  # type: ignore[no-untyped-def]
    clerk = login(CLERK)
    lk = lookups(clerk)
    item_id = clerk.get("/inventory/items/check-serial", params={"serial": "FRX24A0196"}).json()["item_id"]
    item = clerk.get(f"/inventory/items/{item_id}").json()
    assert item["actions"] == ["move", "report_fault"]
    r = clerk.post(f"/inventory/items/{item_id}/actions/send_for_repair", json={"version": item["version"]})
    assert (
        r.status_code == 422
        and r.json()["message"] == "You cannot send for repair this item because it is in stock."
    )
    r = clerk.post(f"/inventory/items/{item_id}/actions/report_fault", json={"version": item["version"]})
    assert r.status_code == 422 and r.json()["details"]["fields"]["reason"] == "Explain the reason."
    item = clerk.post(
        f"/inventory/items/{item_id}/actions/report_fault",
        json={"version": item["version"], "reason": "Cracked screen."},
    ).json()
    assert item["status"] == "FAULTY" and item["actions"] == ["move", "send_for_repair", "dispose"]
    item = clerk.post(
        f"/inventory/items/{item_id}/actions/send_for_repair", json={"version": item["version"]}
    ).json()
    r = clerk.post(
        f"/inventory/items/{item_id}/actions/repaired",
        json={"version": item["version"], "location_id": lk["locations"]["HSA Outram, Gate 2"]},
    )
    assert r.status_code == 422 and r.json()["message"] == "A repaired item goes back to a store."
    item = clerk.post(
        f"/inventory/items/{item_id}/actions/repaired",
        json={"version": item["version"], "location_id": lk["locations"]["NEC Store, Changi"]},
    ).json()
    assert item["status"] == "IN_STOCK" and item["location"]["name"] == "NEC Store, Changi"
    assert [h["kind"] for h in item["history"]][:3] == ["REPAIRED", "SEND_FOR_REPAIR", "REPORT_FAULT"]


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


def test_project_views_and_export(login) -> None:  # type: ignore[no-untyped-def]
    eng = login(ENGINEER)
    rows = {r["project"]["name"]: r for r in eng.get("/inventory/projects").json()}
    hsa = rows["HSA Permit Portal"]
    assert hsa["counts"]["total"] == 21 and hsa["counts"]["in_stock"] == 21
    assert rows["MOM Kiosk Refresh"]["warranty_ending"] == 6
    detail = eng.get(f"/inventory/projects/{hsa['project']['id']}").json()
    assert {c["category_name"]: c["counts"]["total"] for c in detail["by_category"]} == {
        "Camera": 4, "FR reader": 12, "Gateway": 2, "Tablet": 3,
    }  # fmt: skip
    page = eng.get("/inventory/items", params={"project_id": hsa["project"]["id"], "q": "turnstile"}).json()
    assert page["total"] == 4
    soon = eng.get("/inventory/items", params={"warranty_within_days": 60}).json()
    assert soon["total"] == 6 and soon["items"][0]["project"]["name"] == "MOM Kiosk Refresh"
    history = eng.get(f"/inventory/projects/{rows['MOM Kiosk Refresh']['project']['id']}/history").json()
    assert history[0]["kind"] in ("MOVE", "SEND_FOR_REPAIR") and history[0]["serial_no"].startswith("FRX23B")
    xlsx = eng.get("/inventory/export.xlsx", params={"project_id": hsa["project"]["id"]})
    assert xlsx.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert wb.sheetnames == ["Camera", "FR reader", "Gateway", "Tablet"]
    assert [c.value for c in wb["FR reader"][1]][-7:] == [
        "FR ID", "Deployment date", "OS version", "Firmware version", "APK version", "Mounting type", "Remarks",
    ]  # fmt: skip


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
