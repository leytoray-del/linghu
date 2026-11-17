"""Clearing demo data keeps the named people and the reference data, and removes everything else."""

from sqlalchemy import func, select

from erf.db.models import ResourceRequest, Team, User
from erf.db.session import session_scope
from erf.modules.inventory.models import InvItem
from erf.services.demo_cleanup import clear_demo, fingerprint


def test_clear_demo_keeps_named_people_and_reference_data(container) -> None:  # type: ignore[no-untyped-def]
    keep = {fingerprint("admin@example.com"), fingerprint("  Jason   TEO ")}
    with session_scope(container.factory) as s:
        report = clear_demo(s, keep, apply=False)
        assert report.problem is None and report.kept_users == 2 and report.kept_admins == 1
        assert s.scalar(select(func.count()).select_from(ResourceRequest)), "a check changes nothing"

    with session_scope(container.factory) as s:
        lonely = clear_demo(s, {fingerprint("jason.teo@example.com")}, apply=True)
        assert lonely.problem and "administrator" in lonely.problem
    with session_scope(container.factory) as s:
        assert s.scalar(select(func.count()).select_from(User)) > 2, "refused, so nothing was removed"

    with session_scope(container.factory) as s:
        report = clear_demo(s, keep, apply=True)
        assert report.problem is None
    with session_scope(container.factory) as s:
        assert sorted(s.scalars(select(User.email))) == ["admin@example.com", "jason.teo@example.com"]
        assert s.scalar(select(func.count()).select_from(ResourceRequest)) == 0
        assert s.scalar(select(func.count()).select_from(InvItem)) == 0
        assert s.scalar(select(func.count()).select_from(Team)) > 0
