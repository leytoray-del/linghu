"""Clearing demo data before real use.

Everything people did in the system is removed (resource requests, inventory items and withdrawals, emails
waiting to be sent, reference numbers), together with the projects, locations, models and supplier that the
demo created and every user except the ones to keep. Reference data stays: teams, types of support, public
holidays, workflow rules, roles, and kinds of equipment that are in use or were not created by the demo.

The users to keep are named by SHA-256 fingerprints of their email address or full name, so that the
instruction can be committed to a public repository without personal details.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from erf.domain.enums import Role

# Everything people did, in an order that respects the links between tables.
ACTIVITY_TABLES = [
    "inv_withdrawal_events",
    "inv_withdrawal_tasks",
    "inv_withdrawal_items",
    "inv_movements",
    "inv_withdrawals",
    "inv_items",
    "inv_deliveries",
    "approval_tasks",
    "request_changes",
    "request_events",
    "request_preferred_engineers",
    "resource_allocations",
    "resource_requests",
    "notification_outbox",
    "sequences",
]
DEMO_MODELS = ["FRX-200", "FRX-100", "VC-4K", "EG-210", "TX-10"]
DEMO_CATEGORIES = ["CAMERA", "GATEWAY", "TABLET"]
DEMO_PROJECTS = ["P26-0418", "P26-0311", "P26-0502"]
DEMO_LOCATIONS = ["NEC Store, Level 3", "NEC Store, Changi", "HSA Outram, Gate 2"]
DEMO_SUPPLIERS = ["SecureVision Pte Ltd"]


def fingerprint(value: str) -> str:
    """The fingerprint of an email address or a full name: lower case, spaces collapsed."""
    return hashlib.sha256(" ".join(value.lower().split()).encode()).hexdigest()


@dataclass
class CleanupReport:
    kept_users: int = 0
    kept_admins: int = 0
    unmatched_fingerprints: int = 0
    removed: dict[str, int] = field(default_factory=dict)
    remaining: dict[str, int] = field(default_factory=dict)
    problem: str | None = None

    def lines(self) -> list[str]:
        out = [
            f"Users kept: {self.kept_users} (with Administrator: {self.kept_admins})",
            f"Fingerprints that matched nobody: {self.unmatched_fingerprints}",
        ]
        out += [f"Remove from {t}: {n}" for t, n in self.removed.items() if n]
        out += [f"Remaining in {t}: {n}" for t, n in self.remaining.items()]
        if self.problem:
            out.append(f"Stopped: {self.problem}")
        return out


def _count(s: Session, table: str, where: str = "1=1", **params: object) -> int:
    return int(s.execute(text(f"SELECT count(*) FROM {table} WHERE {where}"), params).scalar_one())


def _in(name: str, values: list[str]) -> tuple[str, dict[str, str]]:
    keys = {f"{name}{i}": v for i, v in enumerate(values)}
    return ", ".join(f":{k}" for k in keys), keys


def clear_demo(s: Session, keep: set[str], *, apply: bool) -> CleanupReport:
    """Report what would be removed, and remove it when ``apply`` is set. The caller commits."""
    report = CleanupReport()
    users = s.execute(text("SELECT id, email, display_name FROM users")).all()
    kept = {u.id for u in users if fingerprint(u.email) in keep or fingerprint(u.display_name) in keep}
    matched = {fingerprint(u.email) for u in users if u.id in kept} | {
        fingerprint(u.display_name) for u in users if u.id in kept
    }
    report.kept_users = len(kept)
    report.unmatched_fingerprints = len(keep - matched)
    admins = {
        r.user_id
        for r in s.execute(text("SELECT user_id FROM user_roles WHERE role = :r"), {"r": Role.ADMIN.value})
    }
    active = {r.id for r in s.execute(text("SELECT id FROM users WHERE is_active = 1"))}
    report.kept_admins = len(kept & admins & active)

    removed_users = [u.id for u in users if u.id not in kept]
    uid_list, uid_params = _in("u", [str(i) for i in removed_users] or ["-1"])
    model_list, model_params = _in("m", DEMO_MODELS)
    cat_list, cat_params = _in("c", DEMO_CATEGORIES)
    proj_list, proj_params = _in("p", DEMO_PROJECTS)
    loc_list, loc_params = _in("l", DEMO_LOCATIONS)
    sup_list, sup_params = _in("s", DEMO_SUPPLIERS)

    for t in ACTIVITY_TABLES:
        report.removed[t] = _count(s, t)
    report.removed["inv_models"] = _count(s, "inv_models", f"model_no IN ({model_list})", **model_params)
    report.removed["projects"] = _count(s, "projects", f"code IN ({proj_list})", **proj_params)
    report.removed["locations"] = _count(s, "locations", f"name IN ({loc_list})", **loc_params)
    report.removed["inv_suppliers"] = _count(s, "inv_suppliers", f"name IN ({sup_list})", **sup_params)
    report.removed["users"] = len(removed_users)

    if report.unmatched_fingerprints or report.kept_users != len(keep):
        report.problem = "every person to keep must match exactly one user; nothing was changed."
    elif not report.kept_admins:
        report.problem = (
            "none of the people to keep is an active administrator, so nobody could sign in to manage the "
            "system; nothing was changed."
        )
    if report.problem or not apply:
        return report

    for t in ACTIVITY_TABLES:
        s.execute(text(f"DELETE FROM {t}"))
    s.execute(text(f"DELETE FROM inv_models WHERE model_no IN ({model_list})"), model_params)
    s.execute(
        text(
            f"DELETE FROM inv_categories WHERE code IN ({cat_list}) "
            "AND id NOT IN (SELECT category_id FROM inv_models)"
        ),
        cat_params,
    )
    s.execute(text(f"DELETE FROM inv_suppliers WHERE name IN ({sup_list})"), sup_params)
    s.execute(text(f"DELETE FROM projects WHERE code IN ({proj_list})"), proj_params)
    s.execute(text(f"DELETE FROM locations WHERE name IN ({loc_list})"), loc_params)
    # Projects that stay lose a project manager who is removed; an administrator names a new one.
    s.execute(text(f"UPDATE projects SET pm_user_id = NULL WHERE pm_user_id IN ({uid_list})"), uid_params)
    for t in ("team_approvers", "user_roles", "user_sessions"):
        s.execute(text(f"DELETE FROM {t} WHERE user_id IN ({uid_list})"), uid_params)
    s.execute(text(f"DELETE FROM users WHERE id IN ({uid_list})"), uid_params)
    s.flush()
    broken = s.execute(text("PRAGMA foreign_key_check")).all()
    if broken:
        raise RuntimeError(f"Links between records would break ({len(broken)}); nothing was changed.")
    for t in ("users", "teams", "support_types", "projects", "locations", "inv_categories", "inv_models"):
        report.remaining[t] = _count(s, t)
    return report
