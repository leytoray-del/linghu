"""Approve, return and reject from email links."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select

from erf.db.models import NotificationOutbox
from erf.db.session import session_scope
from tests.integration.test_workflow import new_request

LINK = re.compile(r"https://erf\.test/act/([A-Za-z0-9_\-.]+)\?do=approve")


def mails(container, event: str, to: str) -> list[NotificationOutbox]:  # type: ignore[no-untyped-def]
    with session_scope(container.factory) as s:
        rows = s.scalars(select(NotificationOutbox).where(NotificationOutbox.event_type == event)).all()
        return [r for r in rows if json.loads(r.to_addresses) == [to]]


def token_from(mail: NotificationOutbox) -> str:
    match = LINK.search(mail.body_text)
    assert match, mail.body_text
    return match.group(1)


def submit(login, lookups, **overrides: Any) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    body = new_request(
        lookups, scope_description="Line one of the scope.\nLine two of the scope.", **overrides
    )
    r = login("alex.tan@example.com").post("/requests?submit=true", json=body)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_approver_email_has_full_details_and_personal_links(login, lookups, container) -> None:  # type: ignore[no-untyped-def]
    req = submit(login, lookups)
    [mail] = [
        m
        for m in mails(container, "REQUEST_SUBMITTED", "priya.nair@example.com")
        if req["request_no"] in m.subject
    ]
    html = mail.body_html
    for text in (
        "Line one of the scope.<br>Line two of the scope.",
        "Three days per week.",
        "P26-9999",
        "Man-days awarded",
        "20.0",
    ):
        assert text in html, text
    assert "Approve and assign engineers" in html and "Return to requester" in html and "Reject" in html
    assert (
        "set how much of each person&#39;s time this work needs" in html
        or "set how much of each person's time" in html
    )
    assert "?do=return" in mail.body_text and "?do=reject" in mail.body_text

    [copy] = [
        m
        for m in mails(container, "REQUEST_SUBMITTED", "alex.tan@example.com")
        if req["request_no"] in m.subject
    ]
    assert "/act/" not in copy.body_html and "copy for your information" in copy.body_text


def test_team_leader_and_director_approve_from_email(login, lookups, container, anon) -> None:  # type: ignore[no-untyped-def]
    req = submit(login, lookups)
    token = token_from(
        next(
            m
            for m in mails(container, "REQUEST_SUBMITTED", "priya.nair@example.com")
            if req["request_no"] in m.subject
        )
    )

    view = anon.get(f"/api/v1/email-actions/{token}")
    assert view.status_code == 200, view.text
    data = view.json()
    assert data["step"] == "TL_REVIEW" and data["assignee"]["display_name"] == "Priya Nair"
    assert data["actions"] == ["APPROVE", "RETURN", "REJECT"]
    assert {c["engineer"]["display_name"] for c in data["candidates"]} >= {"Chua Mei Ling", "Nurul Huda"}
    assert data["request"]["scope_description"].startswith("Line one")
    assert (
        login("alex.tan@example.com").get(f"/requests/{req['id']}").json()["status"] == "PENDING_TL_REVIEW"
    ), "opening changes nothing"

    r = anon.post(f"/api/v1/email-actions/{token}", json={"action": "APPROVE"})
    assert r.status_code == 422, "engineers are required"
    e = lookups["engineers"]
    r = anon.post(
        f"/api/v1/email-actions/{token}",
        json={
            "action": "APPROVE",
            "comment": "Mei Ling half time is enough for the first month.",
            "allocations": [
                {"engineer_id": e["Chua Mei Ling"], "allocation_pct": 50},
                {"engineer_id": e["Nurul Huda"], "allocation_pct": 100},
            ],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING_DIRECTOR_APPROVAL" and "director" in r.json()["message"]
    again = anon.post(f"/api/v1/email-actions/{token}", json={"action": "REJECT", "comment": "x"})
    assert again.status_code == 409 and again.json()["code"] == "already_handled"

    detail = login("alex.tan@example.com").get(f"/requests/{req['id']}").json()
    tl_event = next(ev for ev in detail["events"] if ev["action"] == "TL_APPROVE")
    assert tl_event["actor"]["display_name"] == "Priya Nair" and tl_event["payload"]["via"] == "email"
    assert sorted(a["allocation_pct"] for a in detail["allocations"]) == [50, 100]

    director_mail = next(
        m for m in mails(container, "TL_APPROVED", "grace.wong@example.com") if req["request_no"] in m.subject
    )
    assert "Chua Mei Ling (50%, proposed)" in director_mail.body_html
    d = anon.post(f"/api/v1/email-actions/{token_from(director_mail)}", json={"action": "APPROVE"})
    assert d.status_code == 200 and d.json()["status"] == "APPROVED"


def test_return_and_reject_need_a_comment(login, lookups, container, anon) -> None:  # type: ignore[no-untyped-def]
    req = submit(login, lookups)
    token = token_from(
        next(
            m
            for m in mails(container, "REQUEST_SUBMITTED", "priya.nair@example.com")
            if req["request_no"] in m.subject
        )
    )
    assert anon.post(f"/api/v1/email-actions/{token}", json={"action": "RETURN"}).status_code == 422
    r = anon.post(
        f"/api/v1/email-actions/{token}", json={"action": "RETURN", "comment": "Add the site list."}
    )
    assert r.status_code == 200 and r.json()["status"] == "RETURNED"
    gone = anon.get(f"/api/v1/email-actions/{token}")
    assert gone.status_code == 409 and "returned to the requester" in gone.json()["message"]


def test_tampered_and_expired_links(login, lookups, container, anon, clock) -> None:  # type: ignore[no-untyped-def]
    req = submit(login, lookups)
    token = token_from(
        next(
            m
            for m in mails(container, "REQUEST_SUBMITTED", "priya.nair@example.com")
            if req["request_no"] in m.subject
        )
    )
    payload, signature = token.split(".")
    forged = ("x" if payload[0] != "x" else "y") + payload[1:] + "." + signature
    assert anon.get(f"/api/v1/email-actions/{forged}").status_code == 404
    assert anon.get("/api/v1/email-actions/not-a-token").status_code == 404
    clock.advance(days=8)
    expired = anon.get(f"/api/v1/email-actions/{token}")
    assert expired.status_code == 410 and expired.json()["code"] == "link_expired"
    clock.advance(days=-8)


def test_change_review_from_email(login, lookups, container, anon) -> None:  # type: ignore[no-untyped-def]
    pm = login("serene.koh@example.com")
    item = next(
        i
        for i in pm.get("/requests?scope=mine&page_size=100").json()["items"]
        if i["project_name"] == "Archive Storage Upgrade"
    )
    req = pm.get(f"/requests/{item['id']}").json()
    pm.post(
        f"/requests/{req['id']}/changes",
        json={
            "version": req["version"],
            "new_start": req["planned_start"],
            "new_end": "2027-01-15",
            "new_headcount": 2,
            "reason": "Extra data.",
        },
    )
    mail = [m for m in mails(container, "CHANGE_REQUESTED", "priya.nair@example.com")][-1]
    assert "Requested change" in mail.body_html and "Extra data." in mail.body_html
    token = token_from(mail)
    data = anon.get(f"/api/v1/email-actions/{token}").json()
    assert data["step"] == "CHANGE_REVIEW" and data["actions"] == ["APPROVE", "REJECT"]
    assert data["change"]["new_end"] == "2027-01-15"
    assert sorted(p["allocation_pct"] for p in data["preselected"]) == [100, 100]
    r = anon.post(
        f"/api/v1/email-actions/{token}", json={"action": "APPROVE", "allocations": data["preselected"]}
    )
    assert r.status_code == 200, r.text
    after = pm.get(f"/requests/{req['id']}").json()
    assert after["planned_end"] == "2027-01-15" and after["changes"][-1]["status"] == "APPROVED"
