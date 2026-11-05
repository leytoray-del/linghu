"""API entry point: ``uvicorn --factory erf.main:create_app``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm.exc import StaleDataError

from erf.api.container import Container
from erf.api.v1.router import api_router
from erf.core.clock import Clock
from erf.core.config import Settings, get_settings
from erf.core.errors import AppError
from erf.core.logging import configure_logging

log = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, details: dict[str, object] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"code": code, "message": message, "details": details or {}}
    )


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StaleDataError)
    async def stale(_: Request, __: StaleDataError) -> JSONResponse:
        return _error(
            409, "conflict", "Someone else changed this request at the same time. Refresh and try again."
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            fields[".".join(loc) or "request"] = str(err.get("msg", "Invalid value."))
        return _error(422, "validation_failed", "Some fields are not valid.", {"fields": fields})


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built single-page app when no reverse proxy does it (development, small installs)."""
    index = dist / "index.html"
    if not index.is_file():
        log.warning("Frontend directory %s has no index.html; not serving the UI", dist)
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    container = Container.build(settings, clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler = None
        if settings.run_scheduler:
            from erf.jobs.scheduler import start_background

            scheduler = start_background(container.factory, container.clock, settings)
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        container.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.env != "production" else None,
    )
    app.state.container = container
    _install_error_handlers(app)
    app.include_router(api_router)

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict[str, str]:
        with container.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    if settings.frontend_dist:
        _mount_frontend(app, settings.frontend_dist)
    return app
