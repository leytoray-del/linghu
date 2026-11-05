"""Change requests, partial allocations, calendar attachments, digests and the additive migration."""

from __future__ import annotations

import json
import sqlite3
from email import message_from_bytes
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from erf.core.config import Settings
from erf.db.models import NotificationOutbox
from erf.db.session import session_scope
from erf.infrastructure.mail.senders import Attachment, OutgoingMail, SmtpSender
from erf.jobs import tasks

BACKEND = Path(__file__).resolve().parents[2]


def outbox(container, event: str) -> list[NotificationOutbox]:  # type: ignore[no-untyped-def]
    with session_scope(container.factory) as s:
        return list(s.scalars(select(NotificationOutbox).where(NotificationOutbox.event_type == event)))


def find(session, scope: str, project: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    items = session.get(f"/requests?scope={scope}&page_size=100").json()["items"]
    summary = next(i for i in items if i["project_name"] == project)
    return session.get(f"/requests/{summary['id']}").json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------- partial allocation and calendar file


def test_partial_allocation_and_calendar_attachment(login, lookups, container) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.test_workflow import new_request

    pm = login("alex.tan@example.com")
    req = pm.post("/requests?submit=true", json=new_request(lookups)).json()
    tl = login("priya.nair@example.com")

    candidates = {
        c["engineer"]["display_name"]: c for c in tl.get(f"/requests/{req['id']}/candidates").json()
    }
    assert candidates["Ahmad Rahman"]["peak_pct"] == 100, "Ahmad is full time on the archive upgrade"
    assert candidates["Chua Mei Ling"]["peak_pct"] == 0

    bad = [{"engineer_id": lookups["engineers"]["Chua Mei Ling"], "allocation_pct": 30}]
    r = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "APPROVE", "version": req["version"], "allocations": bad},
    )
    assert r.status_code == 422

    allocations = [
        {"engineer_id": lookups["engineers"]["Chua Mei Ling"], "allocation_pct": 50},
        {"engineer_id": lookups["engineers"]["Nurul Huda"], "allocation_pct": 100},
    ]
    req = tl.post(
        f"/requests/{req['id']}/decision",
        json={"action": "APPROVE", "version": req["version"], "allocations": allocations},
    ).json()
    assert sorted(a["allocation_pct"] for a in req["allocations"]) == [50, 100]

    req = (
        login("grace.wong@example.com")
        .post(f"/requests/{req['id']}/decision", json={"action": "APPROVE", "version": req["version"]})
        .json()
    )
    assert req["status"] == "APPROVED"
    mail = outbox(container, "REQUEST_APPROVED")[-1]
    files = json.loads(mail.attachments or "[]")
    assert files[0]["filename"] == f"{req['request_no']}.ics"
    ics = files[0]["content"]
    assert "DTSTART;VALUE=DATE:20261123" in ics and "DTEND;VALUE=DATE:20261219" in ics
    assert "Chua Mei Ling (50%)" in ics.replace("\r\n ", "")
    assert "(50%)" in mail.body_text

    load = login("priya.nair@example.com").get("/resources/load").json()
    meiling = next(e for e in load["engineers"] if e["engineer"]["display_name"] == "Chua Mei Ling")
    assert [a["allocation_pct"] for a in meiling["assignments"]] == [50]


def test_smtp_message_redirect_and_attachment() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        mail_backend="smtp",
        mail_from='"Resource Requests" <sender@example.org>',
        mail_redirect_to="tester@example.org",
    )
    mail = OutgoingMail(
        to=["a@example.com"],
        cc=["b@example.com"],
        subject="ERR-1 approved",
        html="<html><body><p>Hi</p></body></html>",
        text="Hi",
        attachments=[
            Attachment("ERR-1.ics", "text/calendar; method=PUBLISH; charset=UTF-8", "BEGIN:VCALENDAR")
        ],
    )
    msg = message_from_bytes(SmtpSender(settings).build(mail).as_bytes())
    assert msg["To"] == "tester@example.org" and msg["Cc"] is None
    assert "a@example.com" in msg["Subject"]
    parts = {p.get_content_type(): p for p in msg.walk()}
    assert (
        "Intended recipients: To: a@example.com | Cc: b@example.com"
        in parts["text/plain"].get_payload(decode=True).decode()
    )
    cal = parts["text/calendar"]
    assert cal.get_filename() == "ERR-1.ics" and cal.get_param("method") == "PUBLISH"


# ---------------------------------------------------------------- change requests


def test_change_request_flow(login, lookups, container) -> None:  # type: ignore[no-untyped-def]
    pm = login("serene.koh@example.com")
    req = find(pm, "mine", "Archive Storage Upgrade")
    assert req["status"] == "APPROVED" and req["can_request_change"] is True
    body = {
        "version": req["version"],
        "new_start": req["planned_start"],
        "new_end": "2027-01-15",
        "new_headcount": 3,
        "reason": "",
    }
    r = pm.post(f"/requests/{req['id']}/changes", json=body)
    assert r.status_code == 422 and "reason" in r.json()["details"]["fields"]
    assert (
        login("alex.tan@example.com")
        .post(f"/requests/{req['id']}/changes", json={**body, "reason": "x"})
        .status_code
        == 403
    )

    req = pm.post(
        f"/requests/{req['id']}/changes", json={**body, "reason": "Migration volume doubled."}
    ).json()
    change = req["changes"][-1]
    assert change["status"] == "PENDING" and req["can_request_change"] is False
    assert "engineers 2 to 3" in change["summary"]
    assert pm.post(f"/requests/{req['id']}/changes", json={**body, "reason": "again"}).status_code == 409
    assert json.loads(outbox(container, "CHANGE_REQUESTED")[-1].to_addresses) == ["priya.nair@example.com"]

    tl = login("priya.nair@example.com")
    inbox = [i for i in tl.get("/tasks/mine").json() if i["step"] == "CHANGE_REVIEW"]
    assert inbox and "2027" in inbox[0]["change_summary"]
    detail = tl.get(f"/requests/{req['id']}").json()
    assert detail["change_awaiting_me"] == change["id"]

    r = tl.post(f"/requests/{req['id']}/changes/{change['id']}/decision", json={"action": "REJECT"})
    assert r.status_code == 422, "a rejection needs a comment"
    e = lookups["engineers"]
    allocations = [
        {"engineer_id": e["Ahmad Rahman"], "allocation_pct": 100},
        {"engineer_id": e["Kevin Ong"], "allocation_pct": 50},
        {"engineer_id": e["Nurul Huda"], "allocation_pct": 100},
    ]
    req = tl.post(
        f"/requests/{req['id']}/changes/{change['id']}/decision",
        json={"action": "APPROVE", "allocations": allocations},
    ).json()
    assert req["planned_end"] == "2027-01-15" and req["headcount"] == 3
    assert {
        (a["engineer"]["display_name"], a["allocation_pct"], a["status"]) for a in req["allocations"]
    } == {
        ("Ahmad Rahman", 100, "CONFIRMED"),
        ("Kevin Ong", 50, "CONFIRMED"),
        ("Nurul Huda", 100, "CONFIRMED"),
    }
    assert all(a["end_date"] == "2027-01-15" for a in req["allocations"])
    assert req["changes"][-1]["status"] == "APPROVED" and req["can_request_change"] is False
    assert [ev["action"] for ev in req["events"]][-2:] == ["CHANGE_REQUEST", "CHANGE_APPROVE"]
    approved = outbox(container, "CHANGE_APPROVED")[-1]
    assert "nurul.huda@example.com" in json.loads(approved.to_addresses)
    assert "SEQUENCE:1" in json.loads(approved.attachments or "[]")[0]["content"]


def test_change_withdraw_and_cancel_clear_pending_work(login) -> None:  # type: ignore[no-untyped-def]
    pm = login("serene.koh@example.com")
    req = find(pm, "mine", "Archive Storage Upgrade")
    body = {
        "version": req["version"],
        "new_start": req["planned_start"],
        "new_end": "2027-01-08",
        "new_headcount": 2,
        "reason": "Extend.",
    }
    req = pm.post(f"/requests/{req['id']}/changes", json=body).json()
    change_id = req["changes"][-1]["id"]
    req = pm.post(f"/requests/{req['id']}/changes/{change_id}/withdraw").json()
    assert req["changes"][-1]["status"] == "WITHDRAWN" and req["can_request_change"] is True
    assert not [
        i for i in login("priya.nair@example.com").get("/tasks/mine").json() if i["step"] == "CHANGE_REVIEW"
    ]

    req = pm.post(f"/requests/{req['id']}/changes", json={**body, "version": req["version"]}).json()
    req = pm.post(
        f"/requests/{req['id']}/cancel", json={"version": req["version"], "comment": "Project stopped."}
    ).json()
    assert req["status"] == "CANCELLED" and req["changes"][-1]["status"] == "WITHDRAWN"
    assert all(t["status"] != "PENDING" for t in req["tasks"])


# ---------------------------------------------------------------- digests


def test_daily_digest_once_per_working_day(container, clock, settings) -> None:  # type: ignore[no-untyped-def]
    assert tasks.send_daily_digest(container.factory, clock, settings) >= 2
    assert tasks.send_daily_digest(container.factory, clock, settings) == 0, "not twice on the same day"
    rows = outbox(container, "DAILY_DIGEST")
    priya = next(r for r in rows if json.loads(r.to_addresses) == ["priya.nair@example.com"])
    assert "Helpdesk Platform Cut-over" in priya.body_text and "OVERDUE" in priya.body_text
    assert "CSPL Data Migration Phase 2" in priya.body_text

    clock.advance(days=2)  # Saturday
    assert tasks.send_daily_digest(container.factory, clock, settings) == 0
    clock.advance(days=2)  # Monday 9 Nov is a public holiday
    assert tasks.send_daily_digest(container.factory, clock, settings) == 0
    clock.advance(days=1)  # Tuesday
    assert tasks.send_daily_digest(container.factory, clock, settings) >= 2
    clock.advance(days=-5)


def test_weekly_summary_for_directors(container, clock, settings) -> None:  # type: ignore[no-untyped-def]
    assert tasks.send_weekly_summary(container.factory, clock, settings) == 1
    assert tasks.send_weekly_summary(container.factory, clock, settings) == 0
    mail = outbox(container, "WEEKLY_SUMMARY")[0]
    assert json.loads(mail.to_addresses) == ["grace.wong@example.com"]
    assert "HSA Lab Portal Enhancement" in mail.body_text  # waiting for the director
    assert "SHORT-NOTICE" in mail.body_text and "CSPL Data Migration Phase 2" in mail.body_text
    clock.advance(days=7)
    assert tasks.send_weekly_summary(container.factory, clock, settings) == 1
    clock.advance(days=-7)


# ---------------------------------------------------------------- migration 0002 is additive


def test_upgrade_from_0001_keeps_data_without_rebuilding_tables(tmp_path: Path, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
    from erf.api.container import Container
    from erf.core.config import get_settings
    from erf.seed import seed_all

    db = tmp_path / "upgrade.db"
    url = f"sqlite:///{db}"
    monkeypatch.setenv("ERF_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(cfg, "head")
        settings = Settings(_env_file=None, database_url=url)  # type: ignore[call-arg]
        c = Container.build(settings, clock)
        with session_scope(c.factory) as s:
            seed_all(s, settings, demo=True, clock=clock)
        c.engine.dispose()
        command.downgrade(cfg, "0001")  # the schema production runs before this release

        def snapshot() -> tuple[dict[str, int], dict[str, int]]:
            with sqlite3.connect(db) as conn:
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
                    )
                ]
                counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
                pages = dict(
                    conn.execute("SELECT name, rootpage FROM sqlite_master WHERE type='table'").fetchall()
                )
            return counts, pages

        before_counts, before_pages = snapshot()
        assert before_counts["resource_requests"] == 11
        command.upgrade(cfg, "head")
        after_counts, after_pages = snapshot()
        assert after_counts.pop("request_changes") == 0
        assert after_counts == before_counts, "no rows lost or added"
        for table in ("approval_tasks", "notification_outbox", "resource_requests"):
            assert after_pages[table] == before_pages[table], f"{table} was rebuilt"
    finally:
        get_settings.cache_clear()
