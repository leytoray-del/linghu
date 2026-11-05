"""Schedules background jobs, either inside the API process or in a dedicated worker process."""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session, sessionmaker

from erf.core.clock import Clock
from erf.core.config import Settings
from erf.infrastructure.mail.senders import build_sender
from erf.jobs import tasks

log = logging.getLogger(__name__)


def _safe(name: str, fn: Any, *args: Any) -> None:
    try:
        result = fn(*args)
        if result:
            log.info("Job %s processed %s item(s)", name, result)
    except Exception:
        log.exception("Job %s failed", name)


def register_jobs(
    scheduler: BackgroundScheduler | BlockingScheduler,
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
) -> None:
    sender = build_sender(settings)
    common: dict[str, Any] = {"max_instances": 1, "coalesce": True}
    scheduler.add_job(
        _safe, "interval", seconds=30, args=["dispatch_outbox", tasks.dispatch_outbox, factory, clock, sender],
        id="dispatch_outbox", **common,
    )  # fmt: skip
    scheduler.add_job(
        _safe, "cron", minute=5, args=["send_reminders", tasks.send_reminders, factory, clock, settings],
        id="send_reminders", **common,
    )  # fmt: skip
    scheduler.add_job(
        _safe, "cron", hour=0, minute=20, timezone=settings.timezone,
        args=["auto_close", tasks.auto_close, factory, clock, settings], id="auto_close", **common,
    )  # fmt: skip
    scheduler.add_job(
        _safe, "cron", hour=3, minute=40, args=["purge_sessions", tasks.purge_sessions, factory, clock],
        id="purge_sessions", **common,
    )  # fmt: skip


def start_background(factory: sessionmaker[Session], clock: Clock, settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    register_jobs(scheduler, factory, clock, settings)
    scheduler.start()
    log.info("Background jobs started in the API process")
    return scheduler
