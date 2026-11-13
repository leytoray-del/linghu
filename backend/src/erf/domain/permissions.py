"""Permissions, and the roles that grant them.

Endpoints and pages check permissions, never role names, so a role can change or a new module can add
permissions without touching the checks. Each module declares its permissions here under its own prefix.
"""

from __future__ import annotations

from enum import StrEnum

from erf.domain.enums import Role


class Permission(StrEnum):
    # Platform core
    CORE_ADMIN = "core.admin"
    """Users, teams, projects, locations and settings."""

    # Inventory module
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_REGISTER = "inventory.register"
    """Register devices when they arrive, and add a model while doing so."""
    INVENTORY_EDIT = "inventory.edit"
    """Change saved items: their details, location, faults and repairs. Separate from registering."""
    INVENTORY_ADMIN = "inventory.admin"
    """Categories and their fields, models and suppliers."""


_EVERYONE = {Permission.INVENTORY_VIEW}

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.REQUESTER: set(),
    # Engineers register devices when they arrive. Changing saved items is granted separately.
    Role.ENGINEER: {Permission.INVENTORY_REGISTER},
    Role.TEAM_LEADER: set(),
    Role.DIRECTOR: set(),
    Role.VIEWER: set(),
    Role.OPS_MANAGER: set(),
    # Shown as "Inventory editor": people allowed to change items after they are saved.
    Role.INVENTORY_CLERK: {Permission.INVENTORY_REGISTER, Permission.INVENTORY_EDIT},
    Role.ADMIN: {
        Permission.CORE_ADMIN,
        Permission.INVENTORY_REGISTER,
        Permission.INVENTORY_EDIT,
        Permission.INVENTORY_ADMIN,
    },
}


def permissions_for(roles: set[Role]) -> set[Permission]:
    granted = set(_EVERYONE)
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, set())
    return granted
