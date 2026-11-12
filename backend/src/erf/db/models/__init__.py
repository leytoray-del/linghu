"""Importing this package registers every model on ``Base.metadata``."""

from erf.db.models.org import Location, Project
from erf.db.models.request import RequestPreferredEngineer, ResourceRequest
from erf.db.models.settings import Holiday, Sequence, SystemSetting
from erf.db.models.team import SupportType, Team, TeamApprover
from erf.db.models.user import User, UserRole, UserSession
from erf.db.models.workflow import (
    ApprovalTask,
    NotificationOutbox,
    RequestChange,
    RequestEvent,
    ResourceAllocation,
)

__all__ = [
    "ApprovalTask",
    "Holiday",
    "Location",
    "NotificationOutbox",
    "Project",
    "RequestChange",
    "RequestEvent",
    "RequestPreferredEngineer",
    "ResourceAllocation",
    "ResourceRequest",
    "Sequence",
    "SupportType",
    "SystemSetting",
    "Team",
    "TeamApprover",
    "User",
    "UserRole",
    "UserSession",
]

# Module tables are registered on the same metadata, so migrations and tests see every table.
from erf.modules.inventory import models as _inventory_models  # noqa: F401
