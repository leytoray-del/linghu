"""Permissions, the system roles, and what each system role grants by default.

Access is granted in one way only: a role is a set of permissions, and a person has every permission of every
role they hold. Menus, pages, buttons and endpoints check permissions, never role names.

Some permissions are responsibilities rather than access: being a team's reviewer, giving final approval, or
being assignable to work. They decide who can be chosen for those duties and who is emailed, so Administrator
does not get them automatically. Which records a person sees within a permission still follows the data: the
requests they raised, the teams they review, the projects they manage, the work they are assigned to.

Which role grants which permission is kept in the database and can be changed on the Roles and permissions
screen; the defaults below are applied once, when a permission is first introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from erf.domain.enums import Role


class Permission(StrEnum):
    # Platform core
    CORE_ADMIN = "core.admin"
    # Resources module
    RESOURCES_REQUEST = "resources.request"
    RESOURCES_VIEW_ALL = "resources.view_all"
    RESOURCES_LOAD = "resources.load"
    RESOURCES_REPORTS = "resources.reports"
    RESOURCES_PLAN = "resources.plan"
    RESOURCES_MANAGE = "resources.manage"
    RESOURCES_ADMIN = "resources.admin"
    RESOURCES_REVIEW = "resources.review"
    RESOURCES_APPROVE = "resources.approve"
    RESOURCES_ASSIGNABLE = "resources.assignable"
    # Inventory module
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_REGISTER = "inventory.register"
    INVENTORY_EDIT = "inventory.edit"
    INVENTORY_DELETE = "inventory.delete"
    INVENTORY_RETURN = "inventory.return"
    INVENTORY_WITHDRAW = "inventory.withdraw"
    INVENTORY_WITHDRAWALS_ALL = "inventory.withdrawals.all"
    INVENTORY_APPROVE = "inventory.approve"
    INVENTORY_ADMIN = "inventory.admin"


@dataclass(frozen=True)
class PermissionInfo:
    module: str
    label: str
    description: str
    duty: bool = False
    """A responsibility: it puts the person in a pool of approvers or assignable people."""


MODULES: dict[str, str] = {"core": "Platform", "resources": "Resources", "inventory": "Inventory"}

CATALOGUE: dict[Permission, PermissionInfo] = {
    Permission.CORE_ADMIN: PermissionInfo(
        "core",
        "Administration",
        "Users and roles, projects, locations, teams, workflow rules, holidays and email.",
    ),
    Permission.RESOURCES_REQUEST: PermissionInfo(
        "resources", "Raise resource requests", "Ask for engineers' support, and follow one's own requests."
    ),
    Permission.RESOURCES_VIEW_ALL: PermissionInfo(
        "resources",
        "See all resource requests",
        "Every team's requests. Without it, people see their own requests, the teams they review and their "
        "assigned work. Also widens resource load and reports to every team.",
    ),
    Permission.RESOURCES_LOAD: PermissionInfo(
        "resources", "See resource load", "Who is busy when, for the teams the person reviews, or all teams."
    ),
    Permission.RESOURCES_REPORTS: PermissionInfo(
        "resources",
        "See reports",
        "Request numbers and approval times, for the teams the person reviews, or all.",
    ),
    Permission.RESOURCES_PLAN: PermissionInfo(
        "resources", "Plan engineers for any team", "Change the engineers of an approved request in any team."
    ),
    Permission.RESOURCES_MANAGE: PermissionInfo(
        "resources",
        "Manage anyone's requests",
        "Withdraw, cancel or close requests raised by other people.",
    ),
    Permission.RESOURCES_ADMIN: PermissionInfo(
        "resources", "Resource settings", "Types of support, workflow rules and public holidays."
    ),
    Permission.RESOURCES_REVIEW: PermissionInfo(
        "resources",
        "Review a team's requests",
        "Can be chosen as a team's approver, to review its requests and assign engineers.",
        duty=True,
    ),
    Permission.RESOURCES_APPROVE: PermissionInfo(
        "resources",
        "Give final approval of resource requests",
        "Receives every request after the team review, by email and under Approvals.",
        duty=True,
    ),
    Permission.RESOURCES_ASSIGNABLE: PermissionInfo(
        "resources",
        "Can be assigned to requests",
        "Appears in the engineer list of their team and sees the work assigned to them.",
        duty=True,
    ),
    Permission.INVENTORY_VIEW: PermissionInfo(
        "inventory",
        "See the inventory",
        "Inventory list, item details and history, export to Excel, and withdrawals they are involved in.",
    ),
    Permission.INVENTORY_REGISTER: PermissionInfo(
        "inventory", "Register devices", "Register devices when they arrive, and add a model while doing so."
    ),
    Permission.INVENTORY_EDIT: PermissionInfo(
        "inventory", "Edit saved items", "Change the details of an item after it is saved."
    ),
    Permission.INVENTORY_DELETE: PermissionInfo(
        "inventory", "Delete items", "Remove an item from the inventory. Its record and history are kept."
    ),
    Permission.INVENTORY_RETURN: PermissionInfo(
        "inventory", "Return items to stock", "Bring a deployed item back to a store."
    ),
    Permission.INVENTORY_WITHDRAW: PermissionInfo(
        "inventory",
        "Request withdrawals",
        "Request items to be moved to a new location, and add a new site while doing so.",
    ),
    Permission.INVENTORY_WITHDRAWALS_ALL: PermissionInfo(
        "inventory",
        "See all withdrawals",
        "Without it, people see their own requests and those of projects they manage.",
    ),
    Permission.INVENTORY_APPROVE: PermissionInfo(
        "inventory",
        "Give final approval of withdrawals",
        "Receives withdrawals after the project manager approves, by email and under Approvals.",
        duty=True,
    ),
    Permission.INVENTORY_ADMIN: PermissionInfo(
        "inventory",
        "Manage kinds of equipment and models",
        "Kinds of equipment and their fields, models and serial number formats.",
    ),
}


ADMIN_PERMISSIONS = frozenset(p for p in Permission if not CATALOGUE[p].duty)
"""What Administrator always has: everything except responsibilities, which are given through other roles."""

REPLACES: dict[Permission, tuple[str, frozenset[Role]]] = {
    p: ("resources.overview", frozenset({Role.DIRECTOR, Role.VIEWER}))
    for p in (Permission.RESOURCES_VIEW_ALL, Permission.RESOURCES_LOAD, Permission.RESOURCES_REPORTS)
}
"""New permissions that take over an older one, and the roles that had the older one by default. Roles that
hold the older one get the new one; other roles get their defaults, since that access is new to them."""


@dataclass(frozen=True)
class SystemRole:
    name: str
    description: str
    defaults: frozenset[Permission]


P = Permission
_FIELD = frozenset({P.INVENTORY_REGISTER, P.INVENTORY_RETURN, P.INVENTORY_WITHDRAW})
_OVERVIEW = frozenset(
    {P.RESOURCES_VIEW_ALL, P.RESOURCES_LOAD, P.RESOURCES_REPORTS, P.INVENTORY_WITHDRAWALS_ALL}
)

SYSTEM_ROLES: dict[Role, SystemRole] = {
    Role.REQUESTER: SystemRole(
        "Everyone",
        "Every user has this role. It sets what all users can do.",
        frozenset({P.RESOURCES_REQUEST, P.INVENTORY_VIEW}),
    ),
    Role.ENGINEER: SystemRole("Engineer", "Field and support engineers.", _FIELD | {P.RESOURCES_ASSIGNABLE}),
    Role.TEAM_LEADER: SystemRole(
        "Team leader",
        "Reviews requests for the teams they lead.",
        frozenset({P.RESOURCES_REVIEW, P.RESOURCES_LOAD, P.RESOURCES_REPORTS}),
    ),
    Role.DIRECTOR: SystemRole(
        "Director",
        "Gives final approval of resource requests.",
        _OVERVIEW | {P.RESOURCES_PLAN, P.RESOURCES_APPROVE},
    ),
    Role.OPS_MANAGER: SystemRole(
        "Operations manager",
        "Gives final approval of withdrawals.",
        frozenset({P.INVENTORY_WITHDRAWALS_ALL, P.INVENTORY_APPROVE}),
    ),
    Role.INVENTORY_CLERK: SystemRole(
        "Inventory editor", "May change saved items.", _FIELD | {P.INVENTORY_EDIT}
    ),
    Role.VIEWER: SystemRole("Viewer", "Read-only access to everything, for management.", _OVERVIEW),
    Role.ADMIN: SystemRole(
        "Administrator",
        "Full access. This role always has every permission except responsibilities, and cannot be changed.",
        ADMIN_PERMISSIONS,
    ),
}

LOCKED_ROLE = Role.ADMIN
"""The role that always has every permission except responsibilities; its grants are not stored."""
BASE_ROLE = Role.REQUESTER
"""The role every user holds."""
