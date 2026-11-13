"""Inventory use cases: categories and models, registering devices, the item list, editing, deleting, returning, export."""

from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import Select, String, cast, func, or_, select

from erf.core.errors import Conflict, NotFound, ValidationFailed
from erf.db.models import User
from erf.domain.enums import LocationKind
from erf.modules.inventory.domain import (
    OPEN_WITHDRAWAL,
    STATUS_TEXT,
    FieldDef,
    ItemStatus,
    MovementKind,
    WithdrawalStatus,
    check_field_defs,
    clean_attributes,
    normalise_serial,
    serial_matches,
)
from erf.modules.inventory.models import (
    InvCategory,
    InvDelivery,
    InvItem,
    InvModel,
    InvMovement,
    InvSupplier,
    InvWithdrawal,
    InvWithdrawalItem,
)
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
    MovementOut,
    SerialCheckOut,
    StatusCounts,
    SupplierIn,
    SupplierOut,
    WithdrawalRef,
)
from erf.repositories.settings import SettingsRepository
from erf.schemas.common import Page
from erf.services.context import ServiceContext
from erf.services.org_service import OrgService, location_out, project_out
from erf.services.presenters import user_ref

WARRANTY_SOON_DAYS = 60


def category_out(c: InvCategory) -> CategoryOut:
    return CategoryOut(
        id=c.id,
        code=c.code,
        name=c.name,
        fields=[FieldDef.model_validate(f) for f in c.fields or []],
        warranty_required=c.warranty_required,
        is_active=c.is_active,
    )


def item_out(i: InvItem) -> ItemOut:
    return ItemOut(
        id=i.id,
        serial_no=i.serial_no,
        category_id=i.category_id,
        category_name=i.category.name,
        model_id=i.model_id,
        model_no=i.model.model_no,
        project=project_out(i.project),
        location=location_out(i.location),
        status=ItemStatus(i.status),
        warranty_start=i.warranty_start,
        warranty_end=i.warranty_end,
        holder=user_ref(i.holder) if i.holder else None,
        delivery_no=i.delivery.delivery_no if i.delivery else None,
        attributes=dict(i.attributes or {}),
        remarks=i.remarks,
        version=i.version,
    )


def movement_out(m: InvMovement, withdrawal_no: str | None = None) -> MovementOut:
    return MovementOut(
        id=m.id,
        kind=m.kind,
        from_status=m.from_status,
        to_status=m.to_status,
        from_location=m.from_location.name if m.from_location else None,
        to_location=m.to_location.name if m.to_location else None,
        withdrawal_id=m.withdrawal_id,
        withdrawal_no=withdrawal_no,
        changes=m.changes,
        reason=m.reason,
        actor=user_ref(m.actor),
        occurred_at=m.occurred_at,
    )


def delivery_out(d: InvDelivery) -> DeliveryOut:
    return DeliveryOut(
        id=d.id,
        delivery_no=d.delivery_no,
        project=project_out(d.project),
        supplier=SupplierOut.model_validate(d.supplier) if d.supplier else None,
        delivery_order_no=d.delivery_order_no,
        received_on=d.received_on,
        received_by=user_ref(d.received_by),
        location=location_out(d.location),
        item_count=d.item_count,
        remarks=d.remarks,
        created_at=d.created_at,
    )


def _counts(rows: list[tuple[str, int]]) -> StatusCounts:
    c = StatusCounts()
    for status, n in rows:
        key = status.lower()
        if hasattr(c, key):
            setattr(c, key, getattr(c, key) + n)
        c.total += n
    return c


class InventoryService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.s = ctx.session

    # ---- reference data --------------------------------------------------------------------

    def lookups(self) -> InventoryLookups:
        org = OrgService(self.ctx)
        return InventoryLookups(
            categories=[
                category_out(c) for c in self.s.scalars(select(InvCategory).order_by(InvCategory.name))
            ],
            models=[
                ModelOut.model_validate(m)
                for m in self.s.scalars(select(InvModel).order_by(InvModel.model_no))
            ],
            suppliers=[
                SupplierOut.model_validate(x)
                for x in self.s.scalars(select(InvSupplier).order_by(InvSupplier.name))
            ],
            locations=[location_out(loc) for loc in org.locations()],
            projects=[project_out(p) for p in org.projects()],
        )

    def _category(self, category_id: int) -> InvCategory:
        c = self.s.get(InvCategory, category_id)
        if c is None:
            raise NotFound("This category does not exist.")
        return c

    def save_category(self, data: CategoryIn, category_id: int | None = None) -> InvCategory:
        clash = self.s.scalar(select(InvCategory).where(InvCategory.code == data.code))
        if clash is not None and clash.id != category_id:
            raise Conflict(
                "Another category already uses this code.", details={"fields": {"code": "Already used."}}
            )
        c = self._category(category_id) if category_id else InvCategory(tracking="SERIAL")
        old = [FieldDef.model_validate(f) for f in (c.fields or [])]
        problems = check_field_defs(data.fields, old)
        if problems:
            raise ValidationFailed(next(iter(problems.values())), details={"fields": problems})
        c.code = data.code
        c.name = data.name.strip()
        c.fields = [f.model_dump() for f in data.fields]
        c.warranty_required = data.warranty_required
        c.is_active = data.is_active
        if category_id is None:
            self.s.add(c)
        self.s.flush()
        return c

    def save_model(self, data: ModelIn, model_id: int | None = None) -> InvModel:
        self._category(data.category_id)
        model_no = data.model_no.strip()
        clash = self.s.scalar(select(InvModel).where(func.upper(InvModel.model_no) == model_no.upper()))
        if clash is not None and clash.id != model_id:
            raise Conflict(
                "Another model already uses this model number.",
                details={"fields": {"model_no": "Already used."}},
            )
        if data.serial_pattern:
            try:
                re.compile(data.serial_pattern)
            except re.error:
                raise ValidationFailed(
                    "The serial number format is not valid.",
                    details={"fields": {"serial_pattern": "Check the format, for example FRX[0-9A-Z]{7}."}},
                ) from None
        m = self.s.get(InvModel, model_id) if model_id else InvModel()
        if m is None:
            raise NotFound("This model does not exist.")
        if model_id and m.category_id != data.category_id:
            used = self.s.scalar(
                select(func.count()).select_from(InvItem).where(InvItem.model_id == model_id)
            )
            if used:
                raise ValidationFailed(
                    "The category of a model cannot change once items of that model exist."
                )
        m.category_id = data.category_id
        m.model_no = model_no
        m.name = (data.name or "").strip() or None
        m.manufacturer = (data.manufacturer or "").strip() or None
        m.serial_pattern = (data.serial_pattern or "").strip() or None
        m.is_active = data.is_active
        if model_id is None:
            self.s.add(m)
        self.s.flush()
        return m

    def save_supplier(self, data: SupplierIn, supplier_id: int | None = None) -> InvSupplier:
        name = data.name.strip()
        clash = self.s.scalar(select(InvSupplier).where(func.lower(InvSupplier.name) == name.lower()))
        if clash is not None and clash.id != supplier_id:
            raise Conflict(
                "Another supplier already has this name.", details={"fields": {"name": "Already used."}}
            )
        x = self.s.get(InvSupplier, supplier_id) if supplier_id else InvSupplier()
        if x is None:
            raise NotFound("This supplier does not exist.")
        x.name = name
        x.is_active = data.is_active
        if supplier_id is None:
            self.s.add(x)
        self.s.flush()
        return x

    # ---- items -----------------------------------------------------------------------------

    def _item_query(
        self,
        *,
        project_id: int | None,
        category_id: int | None,
        model_id: int | None,
        location_id: int | None,
        q: str | None,
        warranty_within_days: int | None = None,
    ) -> Select[InvItem]:
        """Items matching the filters, excluding deleted items. The status filter is applied separately."""
        query = select(InvItem).where(InvItem.deleted_at.is_(None))
        if project_id:
            query = query.where(InvItem.project_id == project_id)
        if category_id:
            query = query.where(InvItem.category_id == category_id)
        if model_id:
            query = query.where(InvItem.model_id == model_id)
        if location_id:
            query = query.where(InvItem.location_id == location_id)
        if warranty_within_days is not None:
            today = self.ctx.clock.today()
            query = query.where(
                InvItem.warranty_end.is_not(None),
                InvItem.warranty_end >= today,
                InvItem.warranty_end <= today + timedelta(days=warranty_within_days),
            )
        if q:
            like = f"%{q.strip()}%"
            query = query.where(
                or_(
                    InvItem.serial_no.ilike(like),
                    InvItem.remarks.ilike(like),
                    cast(InvItem.attributes, String).ilike(like),
                )
            )
        return query

    def list_items(
        self,
        *,
        project_id: int | None = None,
        category_id: int | None = None,
        status: list[ItemStatus] | None = None,
        model_id: int | None = None,
        location_id: int | None = None,
        q: str | None = None,
        warranty_within_days: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Page[ItemOut]:
        query = self._item_query(
            project_id=project_id,
            category_id=category_id,
            model_id=model_id,
            location_id=location_id,
            q=q,
            warranty_within_days=warranty_within_days,
        )
        if status:
            query = query.where(InvItem.status.in_([s.value for s in status]))
        total = self.s.scalar(select(func.count()).select_from(query.subquery())) or 0
        order = InvItem.warranty_end if warranty_within_days is not None else InvItem.serial_no
        rows = self.s.scalars(
            query.order_by(order, InvItem.id).offset((page - 1) * page_size).limit(page_size)
        )
        return Page(items=[item_out(i) for i in rows], total=total, page=page, page_size=page_size)

    def summary(
        self,
        *,
        project_id: int | None = None,
        category_id: int | None = None,
        model_id: int | None = None,
        location_id: int | None = None,
        q: str | None = None,
    ) -> InventorySummary:
        """Counts by status for the current filters, and how many warranties end soon."""
        base = self._item_query(
            project_id=project_id, category_id=category_id, model_id=model_id, location_id=location_id, q=q
        ).subquery()
        counts = StatusCounts()
        for status, n in self.s.execute(select(base.c.status, func.count()).group_by(base.c.status)).tuples():
            key = status.lower()
            if hasattr(counts, key):
                setattr(counts, key, n)
            counts.total += n
        ending = self._item_query(
            project_id=project_id,
            category_id=category_id,
            model_id=model_id,
            location_id=location_id,
            q=q,
            warranty_within_days=WARRANTY_SOON_DAYS,
        )
        return InventorySummary(
            counts=counts,
            warranty_ending=self.s.scalar(select(func.count()).select_from(ending.subquery())) or 0,
        )

    def _item(self, item_id: int) -> InvItem:
        i = self.s.get(InvItem, item_id)
        if i is None:
            raise NotFound("This item does not exist.")
        return i

    def _live_item(self, item_id: int) -> InvItem:
        i = self._item(item_id)
        if i.deleted_at is not None:
            raise ValidationFailed("This item has been deleted, so it cannot be changed.")
        return i

    def _open_withdrawal(self, item_id: int) -> InvWithdrawal | None:
        return self.s.scalar(
            select(InvWithdrawal)
            .join(InvWithdrawalItem, InvWithdrawalItem.withdrawal_id == InvWithdrawal.id)
            .where(
                InvWithdrawalItem.item_id == item_id,
                InvWithdrawal.status.in_([w.value for w in OPEN_WITHDRAWAL]),
            )
            .limit(1)
        )

    def item_detail(self, item_id: int) -> ItemDetailOut:
        i = self._item(item_id)
        history = list(
            self.s.scalars(
                select(InvMovement)
                .where(InvMovement.item_id == item_id)
                .order_by(InvMovement.occurred_at.desc(), InvMovement.id.desc())
            )
        )
        ids = {m.withdrawal_id for m in history if m.withdrawal_id}
        numbers: dict[int, str] = {}
        if ids:
            rows = self.s.execute(
                select(InvWithdrawal.id, InvWithdrawal.request_no).where(InvWithdrawal.id.in_(ids))
            )
            numbers = {wid: no for wid, no in rows.tuples()}
        w = self._open_withdrawal(i.id)
        deleted_by = self.s.get(User, i.deleted_by_id) if i.deleted_by_id else None
        return ItemDetailOut(
            **item_out(i).model_dump(),
            history=[
                movement_out(m, numbers.get(m.withdrawal_id) if m.withdrawal_id else None) for m in history
            ],
            open_withdrawal=WithdrawalRef(id=w.id, request_no=w.request_no, status=WithdrawalStatus(w.status))
            if w
            else None,
            deleted_at=i.deleted_at,
            deleted_by=user_ref(deleted_by) if deleted_by else None,
            delete_reason=i.delete_reason,
        )

    def find_by_serial(self, serial: str) -> InvItem | None:
        return self.s.scalar(select(InvItem).where(InvItem.serial_no == normalise_serial(serial)))

    def check_serial(self, serial: str) -> SerialCheckOut:
        sn = normalise_serial(serial)
        existing = self.find_by_serial(sn)
        if existing is None:
            return SerialCheckOut(serial_no=sn, exists=False)
        return SerialCheckOut(
            serial_no=sn,
            exists=True,
            item_id=existing.id,
            message=(
                f"{sn} is already registered under {existing.project.name} "
                f"({existing.category.name} {existing.model.model_no})"
                + (", and was deleted." if existing.deleted_at else ".")
            ),
        )

    def _record(self, item: InvItem, user: User, kind: MovementKind, **values: Any) -> None:
        self.s.add(
            InvMovement(
                item_id=item.id, kind=kind.value, actor_id=user.id, occurred_at=self.ctx.clock.now(), **values
            )
        )

    def _check_warranty(
        self, category: InvCategory, start: date | None, end: date | None, prefix: str = ""
    ) -> dict[str, str]:
        problems: dict[str, str] = {}
        if category.warranty_required:
            if start is None:
                problems[f"{prefix}warranty_start"] = "The warranty start date is required for this category."
            if end is None:
                problems[f"{prefix}warranty_end"] = "The warranty end date is required for this category."
        if start and end and end < start:
            problems[f"{prefix}warranty_end"] = "The warranty must end on or after its start date."
        return problems

    def update_item(self, user: User, item_id: int, data: ItemUpdateIn) -> ItemDetailOut:
        i = self._live_item(item_id)
        if i.version != data.version:
            raise Conflict(
                "Someone else changed this item after you opened it. Refresh the page and try again."
            )
        defs = [FieldDef.model_validate(f) for f in i.category.fields or []]
        attrs, problems = clean_attributes(defs, data.attributes, require=True)
        field_problems = {f"attributes.{k}": v for k, v in problems.items()}
        field_problems |= self._check_warranty(i.category, data.warranty_start, data.warranty_end)
        if field_problems:
            raise ValidationFailed("Some fields need attention.", details={"fields": field_problems})
        # Keep values of retired fields: the form does not show them, so they are not sent back.
        for f in defs:
            if f.retired and f.key in (i.attributes or {}):
                attrs[f.key] = i.attributes[f.key]
        labels = {f.key: f.label for f in defs}
        changes: dict[str, Any] = {}

        def note(label: str, old: Any, new: Any) -> None:
            if old != new:
                changes[label] = {"from": old, "to": new}

        note(
            "Warranty start",
            i.warranty_start.isoformat() if i.warranty_start else None,
            data.warranty_start.isoformat() if data.warranty_start else None,
        )
        note(
            "Warranty end",
            i.warranty_end.isoformat() if i.warranty_end else None,
            data.warranty_end.isoformat() if data.warranty_end else None,
        )
        note("Remarks", i.remarks or None, (data.remarks or "").strip() or None)
        old_attrs = dict(i.attributes or {})
        for key in sorted(set(old_attrs) | set(attrs)):
            note(labels.get(key, key), old_attrs.get(key), attrs.get(key))
        if changes:
            i.warranty_start = data.warranty_start
            i.warranty_end = data.warranty_end
            i.remarks = (data.remarks or "").strip() or None
            i.attributes = attrs
            self.s.flush()
            self._record(i, user, MovementKind.UPDATE, changes=changes)
            self.s.flush()
        return self.item_detail(i.id)

    def delete_item(self, user: User, item_id: int, data: ItemDeleteIn) -> ItemDetailOut:
        """Hide an item from lists and searches. The item and its history are kept."""
        i = self._live_item(item_id)
        if i.version != data.version:
            raise Conflict(
                "Someone else changed this item after you opened it. Refresh the page and try again."
            )
        if i.status == ItemStatus.REQUESTED.value:
            w = self._open_withdrawal(i.id)
            raise ValidationFailed(
                f"This item is in withdrawal request {w.request_no if w else ''}. Remove it from the request first."
            )
        reason = data.reason.strip()
        i.deleted_at = self.ctx.clock.now()
        i.deleted_by_id = user.id
        i.delete_reason = reason
        self.s.flush()
        self._record(i, user, MovementKind.DELETE, from_status=i.status, to_status=i.status, reason=reason)
        self.s.flush()
        return self.item_detail(i.id)

    def return_item(self, user: User, item_id: int, data: ItemReturnIn) -> ItemDetailOut:
        """Bring a deployed item back to a store."""
        i = self._live_item(item_id)
        if i.version != data.version:
            raise Conflict(
                "Someone else changed this item after you opened it. Refresh the page and try again."
            )
        if i.status != ItemStatus.DEPLOYED.value:
            raise ValidationFailed(
                f"Only deployed items can be returned. This item is {STATUS_TEXT[ItemStatus(i.status)]}."
            )
        store = OrgService(self.ctx).location(data.location_id)
        if store.kind != LocationKind.STORE.value or not store.is_active:
            raise ValidationFailed(
                "Choose the store the item goes back to.",
                details={"fields": {"location_id": "Choose a store."}},
            )
        before = i.location_id
        i.status = ItemStatus.IN_STOCK.value
        i.location_id = store.id
        self.s.flush()
        self._record(
            i,
            user,
            MovementKind.RETURN,
            from_status=ItemStatus.DEPLOYED.value,
            to_status=ItemStatus.IN_STOCK.value,
            from_location_id=before,
            to_location_id=store.id,
            reason=(data.reason or "").strip() or None,
        )
        self.s.flush()
        self.s.refresh(i)
        return self.item_detail(i.id)

    # ---- deliveries ------------------------------------------------------------------------

    def register_delivery(self, user: User, data: DeliveryIn) -> DeliveryOut:
        org = OrgService(self.ctx)
        project = org.project(data.project_id)
        problems: dict[str, str] = {}
        if not project.is_active:
            problems["project_id"] = "This project is closed. Choose an active project."
        location = org.location(data.location_id)
        if location.kind != LocationKind.STORE.value or not location.is_active:
            problems["location_id"] = "Choose an active store for the delivery."
        if data.supplier_id is not None:
            supplier = self.s.get(InvSupplier, data.supplier_id)
            if supplier is None or not supplier.is_active:
                problems["supplier_id"] = "Choose a supplier from the list."
        models = {
            m.id: m
            for m in self.s.scalars(select(InvModel).where(InvModel.id.in_({x.model_id for x in data.items})))
        }
        serials = [normalise_serial(x.serial_no) for x in data.items]
        existing = {
            i.serial_no: i for i in self.s.scalars(select(InvItem).where(InvItem.serial_no.in_(serials)))
        }
        seen: set[str] = set()
        cleaned: list[tuple[str, InvModel, dict[str, Any]]] = []
        for n, (x, sn) in enumerate(zip(data.items, serials, strict=True)):
            prefix = f"items.{n}."
            model = models.get(x.model_id)
            if model is None or not model.is_active:
                problems[prefix + "model_id"] = "Choose a model from the list."
                continue
            if sn in seen:
                problems[prefix + "serial_no"] = f"{sn} appears more than once in this delivery."
            seen.add(sn)
            if sn in existing:
                other = existing[sn]
                problems[prefix + "serial_no"] = f"{sn} is already registered under {other.project.name}."
            if not serial_matches(model.serial_pattern, sn):
                problems[prefix + "serial_no"] = f"{sn} does not look like a {model.model_no} serial number."
            defs = [FieldDef.model_validate(f) for f in model.category.fields or []]
            attrs, attr_problems = clean_attributes(defs, x.attributes, require=True)
            for key, msg in attr_problems.items():
                problems[f"{prefix}attributes.{key}"] = msg
            problems |= self._check_warranty(model.category, x.warranty_start, x.warranty_end, prefix)
            cleaned.append((sn, model, attrs))
        if problems:
            item_count = len({k.split(".")[1] for k in problems if k.startswith("items.")})
            message = (
                f"{item_count} item{'s' if item_count != 1 else ''} need attention before the delivery can be saved."
                if item_count
                else next(iter(problems.values()))
            )
            raise ValidationFailed(message, details={"fields": problems})

        today = self.ctx.clock.today()
        number = SettingsRepository(self.s).next_sequence("GRN", today.year)
        delivery = InvDelivery(
            delivery_no=f"GRN-{today.year}-{number:04d}",
            project_id=project.id,
            supplier_id=data.supplier_id,
            delivery_order_no=(data.delivery_order_no or "").strip() or None,
            received_on=data.received_on,
            received_by_id=user.id,
            location_id=location.id,
            item_count=len(cleaned),
            remarks=(data.remarks or "").strip() or None,
        )
        self.s.add(delivery)
        self.s.flush()
        for x, (sn, model, attrs) in zip(data.items, cleaned, strict=True):
            item = InvItem(
                serial_no=sn,
                category_id=model.category_id,
                model_id=model.id,
                project_id=project.id,
                location_id=location.id,
                status=ItemStatus.IN_STOCK.value,
                warranty_start=x.warranty_start,
                warranty_end=x.warranty_end,
                delivery_id=delivery.id,
                attributes=attrs,
                remarks=(x.remarks or "").strip() or None,
                created_by_id=user.id,
            )
            self.s.add(item)
            self.s.flush()
            self._record(
                item,
                user,
                MovementKind.RECEIVE,
                to_status=ItemStatus.IN_STOCK.value,
                to_location_id=location.id,
                to_project_id=project.id,
                delivery_id=delivery.id,
            )
        self.s.flush()
        self.s.refresh(delivery)
        return delivery_out(delivery)

    # ---- export ----------------------------------------------------------------------------

    def export_xlsx(self, project_id: int | None) -> bytes:
        query = (
            select(InvItem)
            .where(InvItem.deleted_at.is_(None))
            .order_by(InvItem.project_id, InvItem.category_id, InvItem.serial_no)
        )
        if project_id:
            OrgService(self.ctx).project(project_id)
            query = query.where(InvItem.project_id == project_id)
        items = list(self.s.scalars(query))
        wb = Workbook()
        first = True
        by_category: dict[int, list[InvItem]] = defaultdict(list)
        for i in items:
            by_category[i.category_id].append(i)
        categories = {c.id: c for c in self.s.scalars(select(InvCategory))}
        head_fill = PatternFill("solid", fgColor="1F3A5F")
        for cid, rows in sorted(by_category.items(), key=lambda kv: categories[kv[0]].name) or [(0, [])]:
            ws = wb.active if first else wb.create_sheet()
            assert ws is not None
            first = False
            cat = categories.get(cid)
            ws.title = (cat.name if cat else "Items")[:31]
            defs = [FieldDef.model_validate(f) for f in (cat.fields if cat else [])]
            headers = [
                "Serial no.",
                "Model",
                "Project",
                "Status",
                "Location",
                "Warranty start",
                "Warranty end",
            ]
            headers += [f.label for f in defs] + ["Remarks"]
            ws.append(headers)
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = head_fill
            for i in rows:
                ws.append(
                    [
                        i.serial_no,
                        i.model.model_no,
                        i.project.name,
                        STATUS_TEXT[ItemStatus(i.status)].capitalize(),
                        i.location.name,
                        i.warranty_start,
                        i.warranty_end,
                    ]
                    + [_cell(i.attributes.get(f.key)) for f in defs]
                    + [i.remarks]
                )
            for col in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col)].width = 18
            ws.freeze_panes = "A2"
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()


def _cell(value: Any) -> Any:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return value
