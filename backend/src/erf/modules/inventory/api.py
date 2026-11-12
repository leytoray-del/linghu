"""Inventory API, mounted at /api/v1/inventory."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from erf.api.deps import Ctx, require_permission
from erf.db.models import User
from erf.domain.permissions import Permission
from erf.modules.inventory.domain import ItemAction, ItemStatus
from erf.modules.inventory.schemas import (
    CategoryIn,
    CategoryOut,
    DeliveryIn,
    DeliveryOut,
    InventoryLookups,
    ItemActionIn,
    ItemDetailOut,
    ItemOut,
    ItemUpdateIn,
    ModelIn,
    ModelOut,
    MovementOut,
    ProjectInventoryOut,
    ProjectInventoryRow,
    SerialCheckOut,
    SupplierIn,
    SupplierOut,
)
from erf.modules.inventory.service import InventoryService, category_out
from erf.schemas.common import Page

router = APIRouter(prefix="/inventory", tags=["inventory"])
Viewer = Annotated[User, Depends(require_permission(Permission.INVENTORY_VIEW))]
Clerk = Annotated[User, Depends(require_permission(Permission.INVENTORY_REGISTER))]
InvAdmin = Annotated[User, Depends(require_permission(Permission.INVENTORY_ADMIN))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/lookups", response_model=InventoryLookups)
def lookups(user: Viewer, ctx: Ctx) -> InventoryLookups:
    return InventoryService(ctx).lookups()


@router.get("/projects", response_model=list[ProjectInventoryRow])
def projects(user: Viewer, ctx: Ctx) -> list[ProjectInventoryRow]:
    return InventoryService(ctx).project_list()


@router.get("/projects/{project_id}", response_model=ProjectInventoryOut)
def project(project_id: int, user: Viewer, ctx: Ctx) -> ProjectInventoryOut:
    return InventoryService(ctx).project_inventory(project_id)


@router.get("/projects/{project_id}/history", response_model=list[MovementOut])
def project_history(project_id: int, user: Viewer, ctx: Ctx) -> list[MovementOut]:
    return InventoryService(ctx).project_history(project_id)


@router.get("/items", response_model=Page[ItemOut])
def items(
    user: Viewer,
    ctx: Ctx,
    project_id: int | None = None,
    category_id: int | None = None,
    model_id: int | None = None,
    item_status: Annotated[list[ItemStatus] | None, Query(alias="status")] = None,
    q: str | None = None,
    warranty_within_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[ItemOut]:
    return InventoryService(ctx).list_items(
        project_id=project_id,
        category_id=category_id,
        model_id=model_id,
        status=item_status,
        q=q,
        warranty_within_days=warranty_within_days,
        page=page,
        page_size=page_size,
    )


@router.get("/items/check-serial", response_model=SerialCheckOut)
def check_serial(serial: str, user: Viewer, ctx: Ctx) -> SerialCheckOut:
    return InventoryService(ctx).check_serial(serial)


@router.get("/export.xlsx", response_class=Response)
def export(user: Viewer, ctx: Ctx, project_id: int | None = None) -> Response:
    content = InventoryService(ctx).export_xlsx(project_id)
    name = f"inventory-{ctx.clock.today().isoformat()}.xlsx"
    return Response(
        content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.get("/items/{item_id}", response_model=ItemDetailOut)
def item(item_id: int, user: Viewer, ctx: Ctx) -> ItemDetailOut:
    return InventoryService(ctx).item_detail(item_id)


@router.put("/items/{item_id}", response_model=ItemDetailOut)
def update_item(item_id: int, body: ItemUpdateIn, user: Clerk, ctx: Ctx) -> ItemDetailOut:
    return InventoryService(ctx).update_item(user, item_id, body)


@router.post("/items/{item_id}/actions/{action}", response_model=ItemDetailOut)
def item_action(item_id: int, action: ItemAction, body: ItemActionIn, user: Clerk, ctx: Ctx) -> ItemDetailOut:
    return InventoryService(ctx).act(user, item_id, action, body)


@router.get("/deliveries", response_model=list[DeliveryOut])
def deliveries(user: Viewer, ctx: Ctx, project_id: int | None = None) -> list[DeliveryOut]:
    return InventoryService(ctx).deliveries(project_id)


@router.post("/deliveries", response_model=DeliveryOut, status_code=status.HTTP_201_CREATED)
def register_delivery(body: DeliveryIn, user: Clerk, ctx: Ctx) -> DeliveryOut:
    return InventoryService(ctx).register_delivery(user, body)


# ---- administration of categories, models and suppliers ----


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, user: InvAdmin, ctx: Ctx) -> CategoryOut:
    return category_out(InventoryService(ctx).save_category(body))


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, user: InvAdmin, ctx: Ctx) -> CategoryOut:
    return category_out(InventoryService(ctx).save_category(body, category_id))


# Inventory clerks may add a model while registering a delivery, so a new device type does not wait for an
# administrator. Changing an existing model, and categories, stay with administrators.
@router.post("/models", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def create_model(body: ModelIn, user: Clerk, ctx: Ctx) -> ModelOut:
    return ModelOut.model_validate(InventoryService(ctx).save_model(body))


@router.put("/models/{model_id}", response_model=ModelOut)
def update_model(model_id: int, body: ModelIn, user: InvAdmin, ctx: Ctx) -> ModelOut:
    return ModelOut.model_validate(InventoryService(ctx).save_model(body, model_id))


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierIn, user: InvAdmin, ctx: Ctx) -> SupplierOut:
    return SupplierOut.model_validate(InventoryService(ctx).save_supplier(body))


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierIn, user: InvAdmin, ctx: Ctx) -> SupplierOut:
    return SupplierOut.model_validate(InventoryService(ctx).save_supplier(body, supplier_id))
