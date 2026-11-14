"""Operations command line: ``erf <command>``. Run ``erf --help`` for the list of commands."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config

from erf.core.config import get_settings
from erf.core.logging import configure_logging

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


def cmd_migrate(_: argparse.Namespace) -> None:
    from alembic import command

    command.upgrade(_alembic_config(), "head")
    print("Database is up to date.")


def cmd_seed(args: argparse.Namespace) -> None:
    from erf.api.container import Container
    from erf.db.session import session_scope
    from erf.seed import DEMO_PASSWORD, seed_all

    settings = get_settings()
    if args.demo and settings.env == "production" and not args.force:
        sys.exit("Refusing to load demo accounts in production. Add --force if this is really intended.")
    container = Container.build(settings)
    with session_scope(container.factory) as session:
        print(seed_all(session, settings, demo=args.demo))
    if args.demo:
        print(f"Demo accounts use the password: {DEMO_PASSWORD}")


def cmd_create_admin(args: argparse.Namespace) -> None:
    from erf.api.container import Container
    from erf.core.security import hash_password
    from erf.db.models import User
    from erf.db.session import session_scope
    from erf.domain.enums import Role
    from erf.repositories.users import UserRepository
    from erf.services.admin_service import temporary_password

    container = Container.build(get_settings())
    password = temporary_password()
    with session_scope(container.factory) as session:
        repo = UserRepository(session)
        user = repo.get_by_email(args.email)
        if user is None:
            user = User(email=args.email.lower(), display_name=args.name, is_active=True)
            repo.add(user)
        user.password_hash = hash_password(password)
        user.must_change_password = True
        user.set_roles(user.roles | {Role.ADMIN.value, Role.REQUESTER.value})
    print(f"Administrator {args.email} is ready. Temporary password: {password}")
    print("The password must be changed at first sign-in.")


def cmd_backup(args: argparse.Namespace) -> None:
    """Online backup through the SQLite backup API, safe while the application is running."""
    settings = get_settings()
    if not settings.is_sqlite:
        sys.exit("Backups through this command are only supported for SQLite.")
    source = Path(settings.database_url.split("///", 1)[1])
    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = dest_dir / f"erf-{stamp}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        target.unlink(missing_ok=True)
        sys.exit(f"Backup failed the integrity check: {result}")
    backups = sorted(dest_dir.glob("erf-*.db"))
    for old in backups[: max(0, len(backups) - args.keep)]:
        old.unlink()
    print(f"Backup written to {target} ({target.stat().st_size // 1024} KB); keeping the newest {args.keep}.")


def cmd_run_jobs(_: argparse.Namespace) -> None:
    from erf.api.container import Container
    from erf.infrastructure.mail.senders import build_sender
    from erf.jobs import tasks

    settings = get_settings()
    c = Container.build(settings)
    print("reminders:", tasks.send_reminders(c.factory, c.clock, settings))
    print("daily digests:", tasks.send_daily_digest(c.factory, c.clock, settings))
    print("auto-closed:", tasks.auto_close(c.factory, c.clock, settings))
    print("emails sent:", tasks.dispatch_outbox(c.factory, c.clock, build_sender(settings), batch=100))


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    parser = argparse.ArgumentParser(
        prog="erf", description="Engineering Resource Request system operations."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="Apply database migrations.").set_defaults(func=cmd_migrate)

    p = sub.add_parser("seed", help="Load reference data, and optionally demo accounts and requests.")
    p.add_argument("--demo", action="store_true", help="Also create demo accounts and requests.")
    p.add_argument("--force", action="store_true", help="Allow demo data in production.")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("create-admin", help="Create an administrator or reset one's password.")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Administrator")
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("backup", help="Write an online backup of the SQLite database.")
    p.add_argument("--dest", required=True)
    p.add_argument("--keep", type=int, default=30)
    p.set_defaults(func=cmd_backup)

    sub.add_parser("run-jobs", help="Run reminders, auto-close and email delivery once.").set_defaults(
        func=cmd_run_jobs
    )

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
