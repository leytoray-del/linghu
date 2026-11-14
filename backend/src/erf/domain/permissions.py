"""Permissions, the system roles, and what each system role grants by default.

Pages and endpoints check permissions, never role names. Which role grants which permission is kept in the
database and can be changed by administrators; the defaults below are applied once, when a permission is
first introduced. Roles still carry duties that are not permissions: team leaders review their team's
requests, directors give final approval of resource requests, operations managers give final approval of
withdrawals, and engineers can be assigned to work. Administrator always has every permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from erf.domain.enums import Role


class Permission(StrEnum):
    # Platform core
    CORE_ADMIN = "core.admin"
    # Resources module
    RESOURCES_OVERVIEW = "resources.overview"
    # Inventory module
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_REGISTER = "inventory.register"
    INVENTORY_EDIT = "inventory.edit"
    INVENTORY_DELETE = "inventory.delete"
    INVENTORY_RETURN = "inventory.return"
    INVENTORY_WITHDRAW = "inventory.withdraw"
    INVENTORY_WITHDRAWALS_ALL = "inventory.withdrawals.all"
    INVENTORY_ADMIN = "inventory.admin"


@dataclass(frozen=True)
class PermissionInfo:
    module: str
    label: str
    description: str


MODULES: dict[str, str] = {"core": "Platform", "resources": "Resources", "inventory": "Inventory"}

CATALOGUE: dict[Permission, PermissionInfo] = {
    Permission.CORE_ADMIN: PermissionInfo(
        "core",
        "Administration",
        "Users and roles, projects, locations, teams, workflow rules, holidays and email.",
    ),
    Permission.RESOURCES_OVERVIEW: PermissionInfo(
        "resources",
        "See all resource requests, load and reports",
        "Without it, people see their own requests, and team leaders their teams'.",
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
    Permission.INVENTORY_ADMIN: PermissionInfo(
        "inventory",
        "Manage kinds of equipment and models",
        "Kinds of equipment and their fields, models and serial number formats.",
    ),
}


@dataclass(frozen=True)
class SystemRole:
    name: str
    description: str
    duty: str | None
    """What the role does beyond its permissions, if anything. Shown on the roles screen."""
    defaults: frozenset[Permission]


_FIELD = frozenset(
    {Permission.INVENTORY_REGISTER, Permission.INVENTORY_RETURN, Permission.INVENTORY_WITHDRAW}
)
_VIEW = frozenset({Permission.INVENTORY_VIEW})

SYSTEM_ROLES: dict[Role, SystemRole] = {
    Role.REQUESTER: SystemRole(
        "Everyone",
        "Every user has this role. It sets what all users can do.",
        "Can raise resource requests.",
        _VIEW,
    ),
    Role.ENGINEER: SystemRole(
        "Engineer", "Field and support engineers.", "Can be assigned to resource requests.", _VIEW | _FIELD
    ),
    Role.TEAM_LEADER: SystemRole(
        "Team leader",
        "Reviews requests for the teams they lead.",
        "Reviews and assigns engineers for teams where they are an approver.",
        _VIEW,
    ),
    Role.DIRECTOR: SystemRole(
        "Director",
        "Gives final approval of resource requests.",
        "Gives final approval of resource requests.",
        _VIEW | {Permission.RESOURCES_OVERVIEW, Permission.INVENTORY_WITHDRAWALS_ALL},
    ),
    Role.OPS_MANAGER: SystemRole(
        "Operations manager",
        "Gives final approval of withdrawals.",
        "Gives final approval of equipment withdrawals.",
        _VIEW | {Permission.INVENTORY_WITHDRAWALS_ALL},
    ),
    Role.INVENTORY_CLERK: SystemRole(
        "Inventory editor", "May change saved items.", None, _VIEW | _FIELD | {Permission.INVENTORY_EDIT}
    ),
    Role.VIEWER: SystemRole(
        "Viewer",
        "Read-only access to everything, for management.",
        None,
        _VIEW | {Permission.RESOURCES_OVERVIEW, Permission.INVENTORY_WITHDRAWALS_ALL},
    ),
    Role.ADMIN: SystemRole(
        "Administrator",
        "Full access. This role always has every permission and cannot be changed.",
        None,
        frozenset(Permission),
    ),
}

LOCKED_ROLE = Role.ADMIN
"""The role that always has every permission; its grants are not stored and cannot be edited."""
BASE_ROLE = Role.REQUESTER
"""The role every user holds."""
