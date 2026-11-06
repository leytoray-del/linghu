"""Calendar invitations: approval invites each engineer, changes update or cancel, cancellation removes."""

from __future__ import annotations

import json
from email import message_from_bytes
from typing import Any

from sqlalchemy import select

from erf.core.config import Settings
from erf.db.models import NotificationOutbox
from erf.db.session import session_scope
from erf.infrastructure.mail.senders import Attachment, OutgoingMail, SmtpSender
from tests.integration.test_workflow import new_request

REAL = "jun.wei@acme-engineering.com"


def invites(container, to: str) -> list[NotificationOutbox]:  # type: ignore[no-untyped-def]
    with session_scope(container.factory) as s:
        rows = s.scalars(
            select(NotificationOutbox).where(NotificationOutbox.event_type.like("ASSIGNMENT_%"))
        ).all()
        return [r for r in rows if json.loads(r.to_addresses) == [to]]


def calendar(row: NotificationOutbox) -> str:
    [part] = json.loads(row.attachments or "[]")
    assert part["inline"] is True and part["content_type"].startswith("text/calendar")
    return str(part["content"]).replace("\r\n ", "")


def approved_request(login, lookups, engineer_id: int) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    pm = login("alex.tan@example.com")
    req = pm.post("/requests?submit=true", json=new_request(lookups, headcount=2)).json()
    allocations = [
        {"engineer_id": engineer_id, "allocation_pct": 50},
        {"engineer_id": lookups["engineers"]["Nurul Huda"], "allocation_pct": 100},
    ]
    req = (
        login("priya.nair@example.com")
        .post(
            f"/requests/{req['id']}/decision",
            json={"action": "APPROVE", "version": req["version"], "allocations": allocations},
        )
        .json()
    )
    return (
        login("grace.wong@example.com")
        .post(  # type: ignore[no-any-return]
            f"/requests/{req['id']}/decision", json={"action": "APPROVE", "version": req["version"]}
        )
        .json()
    )


def add_real_engineer(login) -> int:  # type: ignore[no-untyped-def]
    admin = login("admin@example.com")
    support = next(t for t in admin.get("/admin/teams").json() if t["code"] == "SUPPORT")
    r = admin.post(
        "/admin/users",
        json={"email": REAL, "display_name": "Jun Wei", "team_id": support["id"], "roles": ["ENGINEER"]},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["user"]["id"])


def test_full_invitation_lifecycle(login, lookups, container) -> None:  # type: ignore[no-untyped-def]
    jun = add_real_engineer(login)
    req = approved_request(login, lookups, jun)
    assert req["status"] == "APPROVED"

    # 1. Approval: a personal invitation with Jun's own percentage.
    [invite] = invites(container, REAL)
    assert invite.event_type == "ASSIGNMENT_INVITE" and "(50%)" in invite.subject
    ics = calendar(invite)
    for line in (
        "METHOD:REQUEST",
        f"UID:{req['request_no']}@erf",
        "SEQUENCE:0",
        "DTSTART;VALUE=DATE:20261123",
        "DTEND;VALUE=DATE:20261219",
        f"ATTENDEE;CN=Jun Wei;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=FALSE:mailto:{REAL}",
        "ORGANIZER;CN=",
        "X-MICROSOFT-CDO-BUSYSTATUS:FREE",
        "STATUS:CONFIRMED",
    ):
        assert line in ics, line
    assert "- 50%" in ics
    approved = [r for r in invites(container, "alex.tan@example.com")]
    assert approved == [], "the requester gets the normal approval email, not an invitation"

    # 2. A change that drops Jun: his entry is cancelled with a higher sequence.
    pm = login("alex.tan@example.com")
    req = pm.get(f"/requests/{req['id']}").json()
    req = pm.post(
        f"/requests/{req['id']}/changes",
        json={
            "version": req["version"],
            "new_start": "2026-11-23",
            "new_end": "2027-01-08",
            "new_headcount": 1,
            "reason": "Smaller scope.",
        },
    ).json()
    change_id = req["changes"][-1]["id"]
    tl = login("priya.nair@example.com")
    tl.post(
        f"/requests/{req['id']}/changes/{change_id}/decision",
        json={
            "action": "APPROVE",
            "allocations": [{"engineer_id": lookups["engineers"]["Nurul Huda"], "allocation_pct": 100}],
        },
    )
    cancel = invites(container, REAL)[-1]
    assert cancel.event_type == "ASSIGNMENT_CANCELLED"
    ics = calendar(cancel)
    assert "METHOD:CANCEL" in ics and "STATUS:CANCELLED" in ics and "SEQUENCE:1" in ics
    assert f"UID:{req['request_no']}@erf" in ics

    # 3. Another change that adds Jun back: a new invitation with the new period.
    req = pm.get(f"/requests/{req['id']}").json()
    req = pm.post(
        f"/requests/{req['id']}/changes",
        json={
            "version": req["version"],
            "new_start": "2026-11-23",
            "new_end": "2027-01-15",
            "new_headcount": 2,
            "reason": "Scope grew again.",
        },
    ).json()
    change_id = req["changes"][-1]["id"]
    tl.post(
        f"/requests/{req['id']}/changes/{change_id}/decision",
        json={
            "action": "APPROVE",
            "allocations": [
                {"engineer_id": lookups["engineers"]["Nurul Huda"], "allocation_pct": 100},
                {"engineer_id": jun, "allocation_pct": 25},
            ],
        },
    )
    again = invites(container, REAL)[-1]
    assert again.event_type == "ASSIGNMENT_INVITE"
    ics = calendar(again)
    assert (
        "METHOD:REQUEST" in ics
        and "SEQUENCE:2" in ics
        and "DTEND;VALUE=DATE:20270116" in ics
        and "- 25%" in ics
    )

    # 4. A change that keeps Jun: his entry is updated in place.
    req = pm.get(f"/requests/{req['id']}").json()
    req = pm.post(
        f"/requests/{req['id']}/changes",
        json={
            "version": req["version"],
            "new_start": "2026-11-23",
            "new_end": "2027-01-29",
            "new_headcount": 2,
            "reason": "Two more weeks.",
        },
    ).json()
    change_id = req["changes"][-1]["id"]
    tl.post(
        f"/requests/{req['id']}/changes/{change_id}/decision",
        json={
            "action": "APPROVE",
            "allocations": [
                {"engineer_id": lookups["engineers"]["Nurul Huda"], "allocation_pct": 100},
                {"engineer_id": jun, "allocation_pct": 50},
            ],
        },
    )
    update = invites(container, REAL)[-1]
    assert update.event_type == "ASSIGNMENT_UPDATED" and "Your calendar entry is updated" in update.body_text
    ics = calendar(update)
    assert "SEQUENCE:3" in ics and "DTEND;VALUE=DATE:20270130" in ics and "- 50%" in ics

    # 5. Cancelling the approved request removes the entry.
    req = pm.get(f"/requests/{req['id']}").json()
    pm.post(
        f"/requests/{req['id']}/cancel",
        json={"version": req["version"], "comment": "Customer stopped the project."},
    )
    final = invites(container, REAL)[-1]
    assert final.event_type == "ASSIGNMENT_CANCELLED"
    ics = calendar(final)
    assert "METHOD:CANCEL" in ics and "SEQUENCE:4" in ics
    assert "Customer stopped the project." in final.body_text


def test_invitation_is_a_meeting_request_in_the_message() -> None:
    settings = Settings(
        _env_file=None, mail_backend="smtp", mail_from='"Resource Requests" <sender@gmail.com>'
    )  # type: ignore[call-arg]
    mail = OutgoingMail(
        to=[REAL],
        cc=[],
        subject="Assignment",
        html="<html><body>x</body></html>",
        text="x",
        attachments=[
            Attachment(
                "invite.ics",
                "text/calendar; method=REQUEST; charset=UTF-8",
                "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
                inline=True,
            )
        ],
    )
    msg = message_from_bytes(SmtpSender(settings).build(mail).as_bytes())
    assert msg.get_content_type() == "multipart/alternative"
    kinds = [p.get_content_type() for p in msg.walk() if not p.is_multipart()]
    assert kinds == ["text/plain", "text/html", "text/calendar"]
    cal = next(p for p in msg.walk() if p.get_content_type() == "text/calendar")
    assert cal.get_param("method") == "REQUEST" and cal.get_filename() is None
