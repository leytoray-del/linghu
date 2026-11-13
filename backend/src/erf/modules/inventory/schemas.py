from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from erf.modules.inventory.domain import FieldDef, ItemStatus, WithdrawalStatus, WithdrawalStep
from erf.schemas.common import Schema, UserRef
from erf.schemas.org import LocationOut, ProjectOut


class CategoryOut(Schema):
    id: int
    code: str
    name: str
    fields: list[FieldDef]
    warranty_required: bool
    is_active: bool


class CategoryIn(Schema):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    fields: list[FieldDef] = Field(default_factory=list, max_length=40)
    warranty_required: bool = True
    is_active: bool = True


class ModelOut(Schema):
    id: int
    category_id: int
    model_no: str
    name: str | None
    manufacturer: str | None
    serial_pattern: str | None
    is_active: bool


class ModelIn(Schema):
    category_id: int
    model_no: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=120)
    serial_pattern: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class SupplierOut(Schema):
    id: int
    name: str
    is_active: bool


class SupplierIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True


class InventoryLookups(Schema):
    categories: list[CategoryOut]
    models: list[ModelOut]
    suppliers: list[SupplierOut]
    locations: list[LocationOut]
    projects: list[ProjectOut]


class StatusCounts(Schema):
    in_stock: int = 0
    requested: int = 0
    deployed: int = 0
    total: int = 0


class InventorySummary(Schema):
    """Counts for the items matching the current filters (any status)."""

    counts: StatusCounts
    warranty_ending: int


class ItemOut(Schema):
    id: int
    serial_no: str
    category_id: int
    category_name: str
    model_id: int
    model_no: str
    project: ProjectOut
    location: LocationOut
    status: ItemStatus
    warranty_start: date | None
    warranty_end: date | None
    holder: UserRef | None
    delivery_no: str | None
    attributes: dict[str, Any]
    remarks: str | None
    version: int


class MovementOut(Schema):
    id: int
    kind: str
    from_status: str | None
    to_status: str | None
    from_location: str | None
    to_location: str | None
    withdrawal_id: int | None
    withdrawal_no: str | None
    changes: dict[str, Any] | None
    reason: str | None
    actor: UserRef
    occurred_at: datetime


class WithdrawalRef(Schema):
    id: int
    request_no: str
    status: WithdrawalStatus


class ItemDetailOut(ItemOut):
    history: list[MovementOut]
    open_withdrawal: WithdrawalRef | None
    deleted_at: datetime | None
    deleted_by: UserRef | None
    delete_reason: str | None


class ItemUpdateIn(Schema):
    version: int
    warranty_start: date | None = None
    warranty_end: date | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    remarks: str | None = Field(default=None, max_length=2000)


class ItemDeleteIn(Schema):
    version: int
    reason: str = Field(min_length=1, max_length=2000)


class ItemReturnIn(Schema):
    version: int
    location_id: int
    reason: str | None = Field(default=None, max_length=2000)


class DeliveryItemIn(Schema):
    serial_no: str = Field(min_length=1, max_length=64)
    model_id: int
    warranty_start: date | None = None
    warranty_end: date | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    remarks: str | None = Field(default=None, max_length=2000)


class DeliveryIn(Schema):
    project_id: int
    supplier_id: int | None = None
    delivery_order_no: str | None = Field(default=None, max_length=64)
    received_on: date
    location_id: int
    remarks: str | None = Field(default=None, max_length=2000)
    items: list[DeliveryItemIn] = Field(min_length=1, max_length=1000)


class DeliveryOut(Schema):
    id: int
    delivery_no: str
    project: ProjectOut
    supplier: SupplierOut | None
    delivery_order_no: str | None
    received_on: date
    received_by: UserRef
    location: LocationOut
    item_count: int
    remarks: str | None
    created_at: datetime


class SerialCheckOut(Schema):
    serial_no: str
    exists: bool
    message: str | None = None
    item_id: int | None = None


# ---- withdrawals ----


class SiteIn(Schema):
    name: str = Field(min_length=2, max_length=120)


class WithdrawalIn(Schema):
    project_id: int
    item_ids: list[int] = Field(min_length=1, max_length=500)
    to_location_id: int
    reason: str = Field(min_length=1, max_length=2000)


class WithdrawalReviseIn(WithdrawalIn):
    version: int


class WithdrawalDecisionIn(Schema):
    version: int
    approve: bool
    comment: str | None = Field(default=None, max_length=2000)


class WithdrawalVersionIn(Schema):
    version: int
    comment: str | None = Field(default=None, max_length=2000)


class WithdrawalTaskOut(Schema):
    round: int
    step: WithdrawalStep
    status: str
    approvers: list[UserRef]
    decided_by: UserRef | None
    comment: str | None
    decided_at: datetime | None


class WithdrawalEventOut(Schema):
    action: str
    actor: UserRef
    comment: str | None
    occurred_at: datetime


class WithdrawalOut(Schema):
    id: int
    request_no: str
    project: ProjectOut
    requester: UserRef
    to_location: LocationOut
    reason: str
    status: WithdrawalStatus
    item_count: int
    submitted_at: datetime
    completed_at: datetime | None
    waiting_for: list[UserRef]
    version: int


class WithdrawalDetailOut(WithdrawalOut):
    items: list[ItemOut]
    tasks: list[WithdrawalTaskOut]
    events: list[WithdrawalEventOut]
    can_decide: bool
    can_revise: bool
    can_withdraw: bool
