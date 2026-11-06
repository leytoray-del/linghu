from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from erf.db.models import NotificationOutbox
from erf.db.session import session_scope


def new_request(lookups: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "request_type": "PROJECT",
        "priority_declared": "NORMAL",
        "project_name": "Test Rollout",
        "wbs_code": "P26-9999",
        "client_name": "NLB",
        "support_type_id": lookups["types"]["PE"],
        "headcount": 2,
        "man_days": 20,
        "planned_start": "2026-11-23",
        "planned_end": "2026-12-18",
        "scope_description": "Roll out the system.",
        "task_schedule": "Three days per week.",
    }
    body.update(overrides)
    return body


def emails(container, event: str) -> list[NotificationOutbox]:  # type: ignore[no-untyped-def]
    with session_scope(container.factory) as s:
        return list(s.scalars(select(NotificationOutbox).where(NotificationOutbox.event_type == event)))


def test_full_approval_flow(login, lookups, container) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    r = pm.post("/requests?submit=true", json=new_request(lookups))
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "PENDING_TL_REVIEW"
    assert req["request_no"].startswith("ERR-2026-")
    assert req["is_urgent"] is False
    assert req["notice_working_days"] == 10
    assert [h["display_name"] for h in req["current_handlers"]] == ["Priya Nair"]
    submitted = emails(container, "REQUEST_SUBMITTED")
    recipients = [json.loads(m.to_addresses) for m in submitted]
    assert ["priya.nair@example.com"] in recipients, "the approver gets an email with action links"
    assert ["alex.tan@example.com"] in recipients, "the requester gets an information copy"

    tl = login("priya.nair@example.com")
    inbox = tl.get("/tasks/mine").json()
    assert req["id"] in [i["request"]["id"] for i in inbox]
    candidates = tl.get(f"/requests/{req['id']}/candidates").json()
    names = {c["engineer"]["display_name"]: c for c in candidates}
    assert "Ahmad Rahman" in names and "Ravi Kumar" not in names
    assert names["Ahmad Rahman"]["overlapping"], "Ahmad is busy on the archive storage upgrade"

    r = tl.post(f"/requests/{req['id']}/decision", json={"action": "APPROVE", "version": req["version"]})
    assert r.status_code == 422
    ids = [lookups["engineers"]["Chua Mei Ling"], lookups["engineers"]["Nurul Huda"]]
    r = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "APPROVE", "version": req["version"], "engineer_ids": ids},
    )
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["status"] == "PENDING_DIRECTOR_APPROVAL"
    assert {a["status"] for a in req["allocations"]} == {"PROPOSED"}

    director = login("grace.wong@example.com")
    r = director.post(
        f"/requests/{req['id']}/decision", json={"action": "APPROVE", "version": req["version"]}
    )
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["status"] == "APPROVED"
    assert {a["status"] for a in req["allocations"]} == {"CONFIRMED"}
    approved = emails(container, "REQUEST_APPROVED")[-1]
    assert set(json.loads(approved.to_addresses)) == {
        "alex.tan@example.com",
        "meiling.chua@example.com",
        "nurul.huda@example.com",
    }
    assert [e["action"] for e in req["events"]] == ["CREATE", "SUBMIT", "TL_APPROVE", "DIRECTOR_APPROVE"]

    engineer = login("meiling.chua@example.com")
    assigned = engineer.get("/requests?scope=assigned").json()
    assert req["id"] in [i["id"] for i in assigned["items"]]


def test_short_notice_is_urgent_and_needs_justification(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    preview = pm.post("/requests/notice-preview", json={"planned_start": "2026-11-12"}).json()
    assert preview["notice_working_days"] == 3
    assert preview["is_short_notice"] is True
    assert [h["name"] for h in preview["holidays"]] == ["Deepavali (observed)"]

    body = new_request(lookups, planned_start="2026-11-12")
    r = pm.post("/requests?submit=true", json=body)
    assert r.status_code == 422
    assert "urgent_justification" in r.json()["details"]["fields"]

    r = pm.post("/requests?submit=true", json={**body, "urgent_justification": "Go-live moved forward."})
    assert r.status_code == 201
    req = r.json()
    assert req["is_urgent"] is True
    assert req["urgency_reason"] == "SHORT_NOTICE"
    assert req["priority_declared"] == "URGENT"


def test_return_and_resubmit_starts_a_new_round(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    req = pm.post("/requests?submit=true", json=new_request(lookups)).json()
    tl = login("priya.nair@example.com")
    r = tl.post(f"/requests/{req['id']}/decision", json={"action": "RETURN", "version": req["version"]})
    assert r.status_code == 422, "a comment is required"
    req = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "RETURN", "version": req["version"], "comment": "Add the site list."},
    ).json()
    assert req["status"] == "RETURNED"

    req = pm.get(f"/requests/{req['id']}").json()
    assert req["can_edit"] is True
    body = new_request(lookups, task_schedule="Site A on Mon, site B on Wed.", version=req["version"])
    req = pm.put(f"/requests/{req['id']}", json=body).json()
    r = pm.post(f"/requests/{req['id']}/submit", json={"version": req["version"]})
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["status"] == "PENDING_TL_REVIEW"
    assert req["round"] == 2
    assert [t["status"] for t in req["tasks"] if t["round"] == 2] == ["PENDING"]


def test_access_rules(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    req = pm.post("/requests?submit=true", json=new_request(lookups)).json()

    assert login("serene.koh@example.com").get(f"/requests/{req['id']}").status_code == 403
    dev_tl = login("daniel.lim@example.com")
    assert dev_tl.get(f"/requests/{req['id']}").status_code == 403
    assert dev_tl.get("/requests?scope=all").status_code == 403

    r = pm.post(f"/requests/{req['id']}/decision", json={"action": "APPROVE", "version": req["version"]})
    assert r.status_code == 403, "requesters cannot approve their own request"

    pmo = login("pmo@example.com")
    assert pmo.get(f"/requests/{req['id']}").status_code == 200
    assert pmo.get("/reports/summary").status_code == 200
    assert pm.get("/reports/summary").status_code == 403


def test_stale_version_is_rejected(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    req = pm.post("/requests?submit=true", json=new_request(lookups)).json()
    tl = login("priya.nair@example.com")
    r = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "REJECT", "version": req["version"] - 1, "comment": "No."},
    )
    assert r.status_code == 409


def test_second_decision_on_same_step_is_refused(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    req = pm.post("/requests?submit=true", json=new_request(lookups)).json()
    tl = login("priya.nair@example.com")
    done = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "REJECT", "version": req["version"], "comment": "No."},
    ).json()
    r = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "REJECT", "version": done["version"], "comment": "No."},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_transition"


def test_withdraw_releases_proposed_engineers(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("serene.koh@example.com")
    lab = next(
        i
        for i in pm.get("/requests?scope=mine").json()["items"]
        if i["project_name"] == "HSA Lab Portal Enhancement"
    )
    r = pm.post(f"/requests/{lab['id']}/withdraw", json={"version": lab["version"], "comment": "Budget cut."})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "WITHDRAWN"
    assert r.json()["allocations"] == []


def test_drafts_are_private_and_deletable(login, lookups) -> None:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    draft = pm.post("/requests", json={"project_name": "Half done"}).json()
    assert draft["status"] == "DRAFT"
    assert login("grace.wong@example.com").get(f"/requests/{draft['id']}").status_code == 403
    assert pm.client.delete(f"/api/v1/requests/{draft['id']}").status_code == 204


def test_export_and_load(login) -> None:  # type: ignore[no-untyped-def]
    director = login("grace.wong@example.com")
    r = director.get("/requests/export.xlsx?scope=all")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    load = director.get("/resources/load").json()
    assert any(e["assignments"] for e in load["engineers"])
    tl = login("priya.nair@example.com")
    load = tl.get("/resources/load").json()
    assert {e["team_name"] for e in load["engineers"]} == {"Support Team"}
