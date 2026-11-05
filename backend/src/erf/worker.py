"""Optional dedicated worker process: ``python -m erf.worker``.

Use it together with ``ERF_RUN_SCHEDULER=false`` on the API when you want jobs outside the web process.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from erf.api.container import Container
from erf.core.config import get_settings
from erf.core.logging import configure_logging
from erf.jobs.scheduler import register_jobs


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    container = Container.build(settings)
    scheduler = BlockingScheduler(timezone="UTC")
    register_jobs(scheduler, container.factory, container.clock, settings)
    logging.getLogger(__name__).info("Worker started")
    scheduler.start()


if __name__ == "__main__":
    main()
