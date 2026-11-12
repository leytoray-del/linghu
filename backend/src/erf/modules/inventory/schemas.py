from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from erf.modules.inventory.domain import FieldDef, ItemAction, ItemStatus
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
    reserved: int = 0
    issued: int = 0
    deployed: int = 0
    returned: int = 0
    faulty: int = 0
    in_repair: int = 0
    disposed: int = 0
    total: int = 0


class CategoryCounts(Schema):
    category_id: int
    category_name: str
    counts: StatusCounts


class ProjectInventoryRow(Schema):
    project: ProjectOut
    counts: StatusCounts
    warranty_ending: int


class ProjectInventoryOut(Schema):
    project: ProjectOut
    by_category: list[CategoryCounts]
    totals: StatusCounts
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
    from_status: ItemStatus | None
    to_status: ItemStatus | None
    from_location: str | None
    to_location: str | None
    delivery_no: str | None
    changes: dict[str, Any] | None
    reason: str | None
    actor: UserRef
    occurred_at: datetime
    serial_no: str | None = None
    item_id: int | None = None


class ItemDetailOut(ItemOut):
    actions: list[ItemAction]
    history: list[MovementOut]


class ItemUpdateIn(Schema):
    version: int
    warranty_start: date | None = None
    warranty_end: date | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    remarks: str | None = Field(default=None, max_length=2000)


class ItemActionIn(Schema):
    version: int
    location_id: int | None = None
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
