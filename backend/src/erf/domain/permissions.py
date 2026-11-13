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
    """Open the inventory, search, see item details and history, export."""
    INVENTORY_REGISTER = "inventory.register"
    """Register devices when they arrive, and add a model while doing so."""
    INVENTORY_EDIT = "inventory.edit"
    """Change the details of a saved item. Separate from registering."""
    INVENTORY_DELETE = "inventory.delete"
    """Delete an item: it disappears from lists; the item and its history are kept."""
    INVENTORY_RETURN = "inventory.return"
    """Return a deployed item to a store."""
    INVENTORY_WITHDRAW = "inventory.withdraw"
    """Request a withdrawal of items to a new location, and add a new site while doing so."""
    INVENTORY_WITHDRAWALS_ALL = "inventory.withdrawals.all"
    """See every withdrawal request, not only one's own and those of one's projects."""
    INVENTORY_ADMIN = "inventory.admin"
    """Kinds of equipment and their fields, models and suppliers."""
    # Approving a withdrawal is decided by assignment: the PM named on the project approves first, then
    # anyone with the Operations manager role.


_EVERYONE = {Permission.INVENTORY_VIEW}
_FIELD = {Permission.INVENTORY_REGISTER, Permission.INVENTORY_RETURN, Permission.INVENTORY_WITHDRAW}

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.REQUESTER: set(),
    # Engineers register devices when they arrive, request withdrawals and return items to a store.
    Role.ENGINEER: set(_FIELD),
    Role.TEAM_LEADER: set(),
    Role.DIRECTOR: {Permission.INVENTORY_WITHDRAWALS_ALL},
    Role.VIEWER: {Permission.INVENTORY_WITHDRAWALS_ALL},
    Role.OPS_MANAGER: {Permission.INVENTORY_WITHDRAWALS_ALL},
    # Shown as "Inventory editor": people allowed to change items after they are saved.
    Role.INVENTORY_CLERK: _FIELD | {Permission.INVENTORY_EDIT},
    Role.ADMIN: set(Permission),
}


def permissions_for(roles: set[Role]) -> set[Permission]:
    granted = set(_EVERYONE)
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, set())
    return granted
