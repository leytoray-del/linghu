"""Process-wide objects created once at start-up and shared by every request."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from erf.core.clock import Clock
from erf.core.config import Settings
from erf.db.session import build_engine, build_session_factory


@dataclass
class Container:
    settings: Settings
    engine: Engine
    factory: sessionmaker[Session]
    clock: Clock

    @classmethod
    def build(cls, settings: Settings, clock: Clock | None = None) -> Container:
        engine = build_engine(settings.database_url)
        return cls(settings, engine, build_session_factory(engine), clock or Clock(settings.timezone))
