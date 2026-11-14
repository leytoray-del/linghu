from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from erf.api.container import Container
from erf.core.clock import FixedClock
from erf.core.config import Settings
from erf.db.base import Base
from erf.db.session import session_scope
from erf.main import create_app
from erf.seed import DEMO_PASSWORD, seed_all

# Thursday 5 Nov 2026, 10:00 in Singapore (02:00 UTC). Monday 9 Nov is a public holiday.
NOW_UTC = datetime(2026, 11, 5, 2, 0)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        run_scheduler=False,
        base_url="https://erf.test",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def clock(settings: Settings) -> FixedClock:
    return FixedClock(settings.timezone, NOW_UTC)


@pytest.fixture
def container(settings: Settings, clock: FixedClock) -> Container:
    c = Container.build(settings, clock)
    Base.metadata.create_all(c.engine)
    with session_scope(c.factory) as session:
        seed_all(session, settings, demo=True, clock=clock)
    return c


@pytest.fixture
def app(container: Container, settings: Settings, clock: FixedClock):  # type: ignore[no-untyped-def]
    application = create_app(settings, clock)
    application.state.container = container
    return application


class Session:
    """A signed-in browser: its own cookie jar plus the CSRF header the frontend would send."""

    def __init__(self, app, email: str, password: str = DEMO_PASSWORD):  # type: ignore[no-untyped-def]
        self.client = TestClient(app)
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        self.me = r.json()
        self.client.headers["X-CSRF-Token"] = self.client.cookies["erf_csrf"]

    def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.get(f"/api/v1{url}", **kw)

    def post(self, url: str, json=None, **kw):  # type: ignore[no-untyped-def]
        return self.client.post(f"/api/v1{url}", json=json, **kw)

    def put(self, url: str, json=None, **kw):  # type: ignore[no-untyped-def]
        return self.client.put(f"/api/v1{url}", json=json, **kw)

    def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.delete(f"/api/v1{url}", **kw)


@pytest.fixture
def login(app):  # type: ignore[no-untyped-def]
    def _login(email: str, password: str = DEMO_PASSWORD) -> Session:
        return Session(app, email, password)

    return _login


@pytest.fixture
def lookups(login) -> dict:  # type: ignore[no-untyped-def,type-arg]
    data = login("alex.tan@example.com").get("/lookups").json()
    types = {s["code"]: s["id"] for s in data["support_types"]}
    engineers = {e["display_name"]: e["id"] for t in data["teams"] for e in t["engineers"]}
    return {"types": types, "engineers": engineers}


@pytest.fixture
def anon(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    yield TestClient(app)
