"""Importing this package registers every model on ``Base.metadata``."""

from erf.db.models.request import RequestPreferredEngineer, ResourceRequest
from erf.db.models.settings import Holiday, Sequence, SystemSetting
from erf.db.models.team import SupportType, Team, TeamApprover
from erf.db.models.user import User, UserRole, UserSession
from erf.db.models.workflow import ApprovalTask, NotificationOutbox, RequestEvent, ResourceAllocation

__all__ = [
    "ApprovalTask",
    "Holiday",
    "NotificationOutbox",
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
