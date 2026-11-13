"""Inventory API, mounted at /api/v1/inventory."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from erf.api.deps import Ctx, require_permission
from erf.db.models import User
from erf.domain.permissions import Permission
from erf.modules.inventory.domain import ItemStatus, WithdrawalStatus
from erf.modules.inventory.schemas import (
    CategoryIn,
    CategoryOut,
    DeliveryIn,
    DeliveryOut,
    InventoryLookups,
    InventorySummary,
    ItemDeleteIn,
    ItemDetailOut,
    ItemOut,
    ItemReturnIn,
    ItemUpdateIn,
    ModelIn,
    ModelOut,
    SerialCheckOut,
    SiteIn,
    SupplierIn,
    SupplierOut,
    WithdrawalDecisionIn,
    WithdrawalDetailOut,
    WithdrawalIn,
    WithdrawalOut,
    WithdrawalReviseIn,
    WithdrawalVersionIn,
)
from erf.modules.inventory.service import InventoryService, category_out
from erf.modules.inventory.withdrawals import WithdrawalService
from erf.schemas.common import Page
from erf.schemas.org import LocationOut
from erf.services.org_service import location_out

router = APIRouter(prefix="/inventory", tags=["inventory"])
Viewer = Annotated[User, Depends(require_permission(Permission.INVENTORY_VIEW))]
Clerk = Annotated[User, Depends(require_permission(Permission.INVENTORY_REGISTER))]
Editor = Annotated[User, Depends(require_permission(Permission.INVENTORY_EDIT))]
Deleter = Annotated[User, Depends(require_permission(Permission.INVENTORY_DELETE))]
Returner = Annotated[User, Depends(require_permission(Permission.INVENTORY_RETURN))]
Requester = Annotated[User, Depends(require_permission(Permission.INVENTORY_WITHDRAW))]
InvAdmin = Annotated[User, Depends(require_permission(Permission.INVENTORY_ADMIN))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/lookups", response_model=InventoryLookups)
def lookups(user: Viewer, ctx: Ctx) -> InventoryLookups:
    return InventoryService(ctx).lookups()


@router.get("/items", response_model=Page[ItemOut])
def items(
    user: Viewer,
    ctx: Ctx,
    project_id: int | None = None,
    category_id: int | None = None,
    model_id: int | None = None,
    location_id: int | None = None,
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
        location_id=location_id,
        status=item_status,
        q=q,
        warranty_within_days=warranty_within_days,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=InventorySummary)
def summary(
    user: Viewer,
    ctx: Ctx,
    project_id: int | None = None,
    category_id: int | None = None,
    model_id: int | None = None,
    location_id: int | None = None,
    q: str | None = None,
) -> InventorySummary:
    return InventoryService(ctx).summary(
        project_id=project_id, category_id=category_id, model_id=model_id, location_id=location_id, q=q
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
def update_item(item_id: int, body: ItemUpdateIn, user: Editor, ctx: Ctx) -> ItemDetailOut:
    return InventoryService(ctx).update_item(user, item_id, body)


@router.post("/items/{item_id}/delete", response_model=ItemDetailOut)
def delete_item(item_id: int, body: ItemDeleteIn, user: Deleter, ctx: Ctx) -> ItemDetailOut:
    return InventoryService(ctx).delete_item(user, item_id, body)


@router.post("/items/{item_id}/return", response_model=ItemDetailOut)
def return_item(item_id: int, body: ItemReturnIn, user: Returner, ctx: Ctx) -> ItemDetailOut:
    return InventoryService(ctx).return_item(user, item_id, body)


@router.post("/deliveries", response_model=DeliveryOut, status_code=status.HTTP_201_CREATED)
def register_devices(body: DeliveryIn, user: Clerk, ctx: Ctx) -> DeliveryOut:
    """Register devices that arrived: they are saved together as one registration."""
    return InventoryService(ctx).register_delivery(user, body)


# ---- withdrawals ----


@router.get("/withdrawals", response_model=list[WithdrawalOut])
def withdrawals(
    user: Viewer,
    ctx: Ctx,
    scope: Literal["mine", "waiting", "all"] = "mine",
    w_status: Annotated[list[WithdrawalStatus] | None, Query(alias="status")] = None,
) -> list[WithdrawalOut]:
    return WithdrawalService(ctx).list_requests(user, scope, w_status or [])


@router.post("/withdrawals", response_model=WithdrawalDetailOut, status_code=status.HTTP_201_CREATED)
def create_withdrawal(body: WithdrawalIn, user: Requester, ctx: Ctx) -> WithdrawalDetailOut:
    return WithdrawalService(ctx).create(user, body)


@router.get("/withdrawals/{withdrawal_id}", response_model=WithdrawalDetailOut)
def withdrawal(withdrawal_id: int, user: Viewer, ctx: Ctx) -> WithdrawalDetailOut:
    return WithdrawalService(ctx).detail(user, withdrawal_id)


@router.post("/withdrawals/{withdrawal_id}/decision", response_model=WithdrawalDetailOut)
def decide_withdrawal(
    withdrawal_id: int, body: WithdrawalDecisionIn, user: Viewer, ctx: Ctx
) -> WithdrawalDetailOut:
    """Approve or reject. Allowed for the project's PM, then for operations managers."""
    return WithdrawalService(ctx).decide(user, withdrawal_id, body)


@router.put("/withdrawals/{withdrawal_id}", response_model=WithdrawalDetailOut)
def revise_withdrawal(
    withdrawal_id: int, body: WithdrawalReviseIn, user: Requester, ctx: Ctx
) -> WithdrawalDetailOut:
    return WithdrawalService(ctx).revise(user, withdrawal_id, body)


@router.post("/withdrawals/{withdrawal_id}/withdraw", response_model=WithdrawalDetailOut)
def withdraw_withdrawal(
    withdrawal_id: int, body: WithdrawalVersionIn, user: Viewer, ctx: Ctx
) -> WithdrawalDetailOut:
    return WithdrawalService(ctx).withdraw(user, withdrawal_id, body)


@router.post("/sites", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def add_site(body: SiteIn, user: Requester, ctx: Ctx) -> LocationOut:
    """Add a site that is not in the location list yet, while requesting a withdrawal."""
    return location_out(WithdrawalService(ctx).add_site(user, body.name))


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
