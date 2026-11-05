"""Alembic environment. The database URL comes from application settings, never from alembic.ini."""

from __future__ import annotations

from alembic import context

import erf.db.models  # noqa: F401  (registers all tables)
from erf.core.config import get_settings
from erf.db.base import Base
from erf.db.session import build_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is None:
        engine = build_engine(get_settings().database_url)
        with engine.connect() as connection:
            _run(connection)
        engine.dispose()
    else:
        _run(connectable)


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
