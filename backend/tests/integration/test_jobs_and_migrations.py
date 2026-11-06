from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import select

from erf.core.config import Settings
from erf.db.base import Base
from erf.db.models import NotificationOutbox, ResourceRequest
from erf.db.session import build_engine, session_scope
from erf.domain.enums import OutboxStatus
from erf.infrastructure.mail.senders import OutgoingMail
from erf.jobs import tasks

BACKEND = Path(__file__).resolve().parents[2]


class RecordingSender:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[OutgoingMail] = []

    def send(self, mail: OutgoingMail) -> None:
        if self.fail:
            raise ConnectionError("relay unavailable")
        self.sent.append(mail)


def _queue_one(login, lookups) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.test_workflow import new_request

    login("alex.tan@example.com").post("/requests?submit=true", json=new_request(lookups))


def test_outbox_delivery_and_retry(login, lookups, container, clock) -> None:  # type: ignore[no-untyped-def]
    _queue_one(login, lookups)  # one email to the approver and an information copy to the requester
    failing = RecordingSender(fail=True)
    assert tasks.dispatch_outbox(container.factory, clock, failing) == 0
    with session_scope(container.factory) as s:
        rows = s.scalars(select(NotificationOutbox).where(NotificationOutbox.attempts == 1)).all()
        assert len(rows) == 2
        assert all(
            r.status == OutboxStatus.PENDING.value and "relay unavailable" in (r.last_error or "")
            for r in rows
        )

    clock.advance(minutes=5)
    sender = RecordingSender()
    assert tasks.dispatch_outbox(container.factory, clock, sender) == 2
    assert sender.sent[0].to == ["priya.nair@example.com"]
    assert "needs your review" in sender.sent[0].subject
    assert sender.sent[1].to == ["alex.tan@example.com"]


def test_reminders_for_overdue_tasks(container, clock, settings) -> None:  # type: ignore[no-untyped-def]
    # Only urgent tasks get individual reminders. The seeded urgent "CSPL Data Migration Phase 2" was
    # submitted yesterday afternoon with a four-hour deadline, so it is overdue now.
    assert tasks.send_reminders(container.factory, clock, settings) >= 1
    assert tasks.send_reminders(container.factory, clock, settings) == 0, "not again within the interval"
    with session_scope(container.factory) as s:
        rows = s.scalars(
            select(NotificationOutbox).where(NotificationOutbox.event_type == "TASK_REMINDER")
        ).all()
        assert any("CSPL Data Migration Phase 2" in r.subject for r in rows)
        assert not any("Helpdesk Platform Cut-over" in r.subject for r in rows), (
            "normal tasks go in the digest"
        )


def test_auto_close_after_planned_end(container, clock, settings) -> None:  # type: ignore[no-untyped-def]
    clock.advance(days=60)
    assert tasks.auto_close(container.factory, clock, settings) >= 1
    with session_scope(container.factory) as s:
        kiosk = s.scalars(
            select(ResourceRequest).where(ResourceRequest.project_name == "Smart Library Kiosk PoC")
        ).one()
        assert kiosk.status == "CLOSED"
    clock.advance(days=-60)


def test_migrations_match_models(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("ERF_DATABASE_URL", url)
    from erf.core.config import get_settings

    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(cfg, "head")
        engine = build_engine(url)
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        # Migration 0002 adds approval_tasks.change_id in place with a column-level foreign key, so no
        # table is rebuilt. SQLAlchemy cannot read the name of such a constraint back from SQLite and
        # reports it as removed and re-added; the constraint itself exists.
        diff = [
            d
            for d in diff
            if not (
                d[0] in ("add_fk", "remove_fk")
                and d[1].parent.name == "approval_tasks"
                and [c.name for c in d[1].columns] == ["change_id"]
            )
        ]
        assert diff == [], diff
        command.downgrade(cfg, "base")
    finally:
        get_settings.cache_clear()


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.timezone == "Asia/Singapore"
    assert s.mail_backend == "log"
    assert timedelta(hours=s.session_ttl_hours) == timedelta(hours=12)
