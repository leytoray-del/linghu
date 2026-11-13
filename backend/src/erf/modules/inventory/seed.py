"""Inventory reference data (the FR reader category) and demo data."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from erf.core.clock import Clock
from erf.core.config import Settings
from erf.db.models import Location, NotificationOutbox, Project, User
from erf.domain.enums import LocationKind, OutboxStatus
from erf.modules.inventory.models import InvCategory, InvItem, InvModel, InvSupplier
from erf.modules.inventory.schemas import DeliveryIn, DeliveryItemIn, WithdrawalDecisionIn, WithdrawalIn
from erf.modules.inventory.service import InventoryService
from erf.modules.inventory.withdrawals import WithdrawalService
from erf.services.context import ServiceContext

log = logging.getLogger(__name__)

MOUNTING = ["Wall", "Pedestal", "Turnstile", "Desk", "Other"]

# The FR reader category, with the fields named in the requirement. Created once; the administrator
# can change it afterwards.
FR_READER: tuple[str, str, list[dict[str, Any]]] = (
    "FR_READER",
    "FR reader",
    [
        {"key": "fr_id", "label": "FR ID", "type": "text", "show_in_list": True},
        {"key": "deployment_date", "label": "Deployment date", "type": "date"},
        {"key": "os_version", "label": "OS version", "type": "text"},
        {"key": "firmware_version", "label": "Firmware version", "type": "text", "show_in_list": True},
        {"key": "apk_version", "label": "APK version", "type": "text", "show_in_list": True},
        {
            "key": "mounting_type",
            "label": "Mounting type",
            "type": "choice",
            "choices": MOUNTING,
            "show_in_list": True,
        },
    ],
)

DEMO_CATEGORIES: list[tuple[str, str, list[dict[str, Any]]]] = [
    (
        "CAMERA",
        "Camera",
        [
            {
                "key": "resolution",
                "label": "Resolution",
                "type": "choice",
                "choices": ["2 MP", "5 MP", "4K"],
                "show_in_list": True,
            },
            {"key": "lens", "label": "Lens", "type": "text", "show_in_list": True},
            {"key": "outdoor_rated", "label": "Outdoor rated", "type": "boolean", "show_in_list": True},
        ],
    ),
    (
        "GATEWAY",
        "Gateway",
        [
            {"key": "firmware_version", "label": "Firmware version", "type": "text", "show_in_list": True},
            {"key": "ports", "label": "Ports", "type": "number", "show_in_list": True},
        ],
    ),
    (
        "TABLET",
        "Tablet",
        [
            {"key": "os_version", "label": "OS version", "type": "text", "show_in_list": True},
            {"key": "managed_by_mdm", "label": "Managed by MDM", "type": "boolean", "show_in_list": True},
        ],
    ),
]


def _complete(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    defaults = {"choices": [], "required": False, "show_in_list": False, "retired": False}
    return [{**defaults, **f} for f in fields]


def seed_inventory_reference(session: Session) -> None:
    code, name, fields = FR_READER
    if session.scalar(select(InvCategory).where(InvCategory.code == code)) is None:
        session.add(
            InvCategory(
                code=code, name=name, tracking="SERIAL", fields=_complete(fields), warranty_required=True
            )
        )
        session.flush()


def seed_inventory_demo(
    session: Session, settings: Settings, users: dict[str, User], today: date, clock: Clock | None = None
) -> int:
    if session.scalar(select(InvItem.id).limit(1)) is not None:
        log.info("Inventory items already exist; demo inventory was not added")
        return 0
    cats = {c.code: c for c in session.scalars(select(InvCategory))}
    for code, name, fields in DEMO_CATEGORIES:
        if code not in cats:
            cats[code] = InvCategory(
                code=code, name=name, tracking="SERIAL", fields=_complete(fields), warranty_required=True
            )
            session.add(cats[code])
    session.flush()

    def project(code: str, name: str, client: str, pm: str) -> Project:
        p = session.scalar(select(Project).where(Project.code == code))
        if p is None:
            p = Project(code=code, name=name, client_name=client, pm_user_id=users[pm].id, is_active=True)
            session.add(p)
        return p

    hsa = project("P26-0418", "HSA Permit Portal", "HSA", "pm1")
    cspl = project("P26-0311", "CSPL Data Migration", "CSPL", "pm2")
    mom = project("P26-0502", "MOM Kiosk Refresh", "MOM", "pm1")

    def location(name: str, kind: LocationKind) -> Location:
        loc = session.scalar(select(Location).where(Location.name == name))
        if loc is None:
            loc = Location(name=name, kind=kind.value, is_active=True)
            session.add(loc)
        return loc

    store = location("NEC Store, Level 3", LocationKind.STORE)
    location("NEC Store, Changi", LocationKind.STORE)
    site = location("HSA Outram, Gate 2", LocationKind.SITE)

    def model(no: str, cat: str, maker: str, pattern: str | None) -> InvModel:
        m = session.scalar(select(InvModel).where(InvModel.model_no == no))
        if m is None:
            m = InvModel(
                model_no=no,
                category_id=cats[cat].id,
                manufacturer=maker,
                serial_pattern=pattern,
                is_active=True,
            )
            session.add(m)
        return m

    frx200 = model("FRX-200", "FR_READER", "SecureVision", r"FRX[0-9]{2}[A-Z][0-9]{4}")
    frx100 = model("FRX-100", "FR_READER", "SecureVision", r"FRX[0-9]{2}[A-Z][0-9]{4}")
    cam = model("VC-4K", "CAMERA", "Vistacam", r"CAM[0-9A-Z]{7}")
    gw = model("EG-210", "GATEWAY", "Gatelink", None)
    tab = model("TX-10", "TABLET", "Tabtronic", None)
    supplier = session.scalar(select(InvSupplier).where(InvSupplier.name == "SecureVision Pte Ltd"))
    if supplier is None:
        supplier = InvSupplier(name="SecureVision Pte Ltd", is_active=True)
        session.add(supplier)
    session.flush()

    ctx = ServiceContext(session, clock or Clock(settings.timezone), settings)
    svc = InventoryService(ctx)
    clerk = users["clerk"]
    w_start, w_end = today - timedelta(days=40), today - timedelta(days=40) + timedelta(days=3 * 365)
    old_start, old_end = date(2023, 12, 1), today + timedelta(days=25)

    def deliver(p: Project, items: list[DeliveryItemIn], received: date, do: str) -> None:
        svc.register_delivery(
            clerk,
            DeliveryIn(
                project_id=p.id,
                supplier_id=supplier.id,
                delivery_order_no=do,
                received_on=received,
                location_id=store.id,
                items=items,
            ),
        )

    readers = [
        DeliveryItemIn(
            serial_no=f"FRX24A{193 + n:04d}",
            model_id=frx200.id,
            warranty_start=w_start,
            warranty_end=w_end,
            attributes={
                "firmware_version": "4.2.1",
                "apk_version": "2.8.0",
                "mounting_type": "Pedestal" if n % 3 else "Turnstile",
            },
        )
        for n in range(12)
    ]
    cams = [
        DeliveryItemIn(serial_no=f"CAM8K20{311 + n:03d}", model_id=cam.id, warranty_start=w_start, warranty_end=w_end,
                       attributes={"resolution": "4K", "lens": "2.8 mm", "outdoor_rated": n % 2 == 0})
        for n in range(4)
    ]  # fmt: skip
    deliver(hsa, readers + cams, today - timedelta(days=40), "DO-55102")
    deliver(
        hsa,
        [DeliveryItemIn(serial_no=f"GW1A000{412 + n}", model_id=gw.id, warranty_start=w_start, warranty_end=w_end,
                        attributes={"firmware_version": "1.14", "ports": 8}) for n in range(2)]
        + [DeliveryItemIn(serial_no=f"TAB7Q55{120 + n}", model_id=tab.id, warranty_start=w_start, warranty_end=w_end,
                          attributes={"os_version": "Android 14", "managed_by_mdm": True}) for n in range(3)],
        today - timedelta(days=20),
        "DO-55187",
    )  # fmt: skip
    deliver(
        mom,
        [DeliveryItemIn(serial_no=f"FRX23B{451 + n:04d}", model_id=frx100.id, warranty_start=old_start, warranty_end=old_end,
                        attributes={"fr_id": f"FR-{451 + n}", "firmware_version": "3.9.4", "apk_version": "2.6.3", "mounting_type": "Wall"})
         for n in range(6)],
        today - timedelta(days=700),
        "DO-41002",
    )  # fmt: skip
    deliver(
        cspl,
        [DeliveryItemIn(serial_no=f"FRX24C{102 + n:04d}", model_id=frx200.id, warranty_start=w_start, warranty_end=w_end,
                        attributes={"firmware_version": "4.2.1", "apk_version": "2.8.0"}) for n in range(5)],
        today - timedelta(days=10),
        "DO-55230",
    )  # fmt: skip

    # Demo history must not send real emails: only the emails queued from here on are marked as not delivered.
    last_email = session.scalar(select(func.max(NotificationOutbox.id))) or 0
    # Two withdrawals: one approved (the readers are now deployed at the site), one waiting for the PM.
    wsvc = WithdrawalService(ctx)
    engineer, pm, om = users["e_jason"], users["pm1"], users["ops"]

    def ids(*serials: str) -> list[int]:
        found = [svc.find_by_serial(sn) for sn in serials]
        return [i.id for i in found if i is not None]

    done = wsvc.create(
        engineer,
        WithdrawalIn(project_id=hsa.id, item_ids=ids("FRX24A0194", "FRX24A0195"), to_location_id=site.id,
                     reason="Install at Gate 2 for the pilot."),
    )  # fmt: skip
    done = wsvc.decide(pm, done.id, WithdrawalDecisionIn(version=done.version, approve=True))
    wsvc.decide(om, done.id, WithdrawalDecisionIn(version=done.version, approve=True, comment="Go ahead."))
    wsvc.create(
        engineer,
        WithdrawalIn(project_id=hsa.id, item_ids=ids("CAM8K20311"), to_location_id=site.id,
                     reason="Camera for the Gate 2 lane."),
    )  # fmt: skip
    session.flush()
    session.execute(
        update(NotificationOutbox)
        .where(NotificationOutbox.id > last_email, NotificationOutbox.status == OutboxStatus.PENDING.value)
        .values(status=OutboxStatus.SKIPPED.value, last_error="Demo data: not delivered.")
    )
    return session.scalar(select(InvItem.id).order_by(InvItem.id.desc()).limit(1)) or 0
