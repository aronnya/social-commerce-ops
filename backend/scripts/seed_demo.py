"""Load a synthetic recruiter/demo dataset through domain services.

Safety:
  ALLOW_DEMO_SEED=1
  DEMO_DATABASE_URL or DATABASE_URL must be loopback and the database name
  must contain "demo" or "test".

Repeatability:
  Pass --reset to TRUNCATE application tables with RESTART IDENTITY, then seed.
  Alembic revision is left intact.

This script does not modify application workflows. It only calls existing
service operations.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import normalize_database_url
from app.models import (
    Customer,
    Enquiry,
    Fulfilment,
    InventoryLot,
    Payment,
    Preorder,
    Product,
    Supplier,
    SupplierOrder,
    SupplierOrderAllocation,
    SupplierOrderLine,
)
from app.schemas import (
    CustomerCreate,
    EnquiryCreate,
    EnquiryUpdate,
    FulfilmentCreate,
    PaymentCreate,
    PaymentMethod,
    PreorderCreate,
    PreorderTransition,
    ProductCreate,
    SupplierCreate,
    SupplierOrderReconcile,
    SupplierOrderTransition,
    ReconciliationLineInput,
)
from app import services
from scripts.demo_safety import UnsafeDemoTargetError, assert_demo_seed_allowed

DEMO_MARKER = "SYNTHETIC DEMO — fictional recruiter dataset"
UTC = timezone.utc

# Display names used on operational screens. Keep these fictional and specific
# so lists never fall back to "Customer #1" / "Product #1" style labels when
# reference data loads from this dataset.
DEMO_SUPPLIERS = (
    {
        "name": "Crescent Textiles",
        "contact_name": "Amira Shah",
        "email": "crescent.desk@example.test",
    },
    {
        "name": "Noor Fashion Supply",
        "contact_name": "Bilal Hussain",
        "email": "noor.desk@example.test",
    },
    {
        "name": "Sapphire Wholesale",
        "contact_name": "Ciara Flynn",
        "email": "sapphire.desk@example.test",
    },
)

# Truncated on --reset. RESTART IDENTITY rewinds serials so a second seed is
# not Customer #22 / Preorder #29.
APPLICATION_TABLES = (
    "fulfilments",
    "inventory_lots",
    "supplier_order_allocations",
    "supplier_order_lines",
    "supplier_orders",
    "payments",
    "preorders",
    "enquiries",
    "products",
    "customers",
    "suppliers",
)

DEMO_CUSTOMERS = (
    {"name": "Aisha Rahman", "facebook_name": "Aisha Rahman", "phone": "00000 000001"},
    {"name": "Sara Malik", "facebook_name": "Sara Malik", "phone": "00000 000002"},
    {"name": "Emma Walsh", "facebook_name": "Emma Walsh", "phone": "00000 000003"},
    {"name": "Nadia Hassan", "facebook_name": "Nadia Hassan", "phone": "00000 000004"},
    {"name": "Lina Costa", "facebook_name": "Lina Costa", "phone": "00000 000005"},
    {"name": "Hannah Byrne", "facebook_name": "Hannah Byrne", "phone": "00000 000006"},
    {"name": "Yasmin Qureshi", "facebook_name": "Yasmin Qureshi", "phone": "00000 000007"},
    {"name": "Priya Nair", "facebook_name": "Priya Nair", "phone": "00000 000008"},
    {"name": "Chloe Brennan", "facebook_name": "Chloe Brennan", "phone": "00000 000009"},
    {"name": "Fatima Ali", "facebook_name": "Fatima Ali", "phone": "00000 000010"},
    {"name": "Maya Keane", "facebook_name": "Maya Keane", "phone": "00000 000011"},
    {"name": "Olivia Brogan", "facebook_name": "Olivia Brogan", "phone": "00000 000012"},
)


def _dt(days_ago: int, hour: int = 10) -> datetime:
    now = datetime(2026, 9, 1, hour, 0, tzinfo=UTC)
    return now - timedelta(days=days_ago)


def _wipe_application_tables(db: Session) -> None:
    quoted = ", ".join(APPLICATION_TABLES)
    db.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    db.commit()


def _enquiry(
    db: Session,
    customer_id: int,
    product_id: int,
    *,
    quantity: int = 1,
    days_ago: int = 10,
    outcome: str | None = None,
    notes: str | None = None,
) -> Enquiry:
    enquiry = services.create_enquiry(
        db,
        EnquiryCreate(
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            notes=notes or DEMO_MARKER,
            enquired_at=_dt(days_ago),
        ),
    )
    if outcome is not None:
        enquiry = services.update_enquiry(
            db, enquiry.id, EnquiryUpdate(outcome=outcome)
        )
    return enquiry


def _preorder_from_enquiry(
    db: Session,
    enquiry: Enquiry,
    *,
    notes: str | None = None,
) -> Preorder:
    return services.create_preorder(
        db,
        PreorderCreate(
            customer_id=enquiry.customer_id,
            product_id=enquiry.product_id,
            enquiry_id=enquiry.id,
            quantity=enquiry.quantity,
            notes=notes or DEMO_MARKER,
        ),
    )


def _pay(
    db: Session,
    preorder_id: int,
    amount: str,
    method: PaymentMethod = "BANK_TRANSFER",
    reference: str = "DEMO-PAY",
) -> None:
    services.create_payment(
        db,
        preorder_id,
        PaymentCreate(
            amount=Decimal(amount),
            method=method,
            reference=reference,
            notes=DEMO_MARKER,
        ),
    )


def _draft(db: Session, supplier_id: int, preorder_ids: list[int]) -> SupplierOrder:
    return services.generate_supplier_order_draft(db, supplier_id, preorder_ids)


def _advance(db: Session, order_id: int, until: str) -> SupplierOrder:
    order = services.place_supplier_order(db, order_id)
    if until == "PLACED":
        return order
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        order = services.transition_supplier_order(
            db, order_id, SupplierOrderTransition(status=status)  # type: ignore[arg-type]
        )
        if status == until:
            return order
    return order


def _reconcile_all(db: Session, order: SupplierOrder, received_by_line: dict[int, int]) -> None:
    payload = SupplierOrderReconcile(
        lines=[
            ReconciliationLineInput(
                line_id=line.id,
                received_quantity=received_by_line[line.id],
            )
            for line in order.lines
        ],
        reconciliation_notes=DEMO_MARKER,
    )
    services.reconcile_supplier_order(db, order.id, payload)


def seed_demo_data(db: Session) -> dict[str, int]:
    """Insert the synthetic dataset using domain operations. Caller owns wipe."""
    crescent = services.create_supplier(
        db,
        SupplierCreate(**DEMO_SUPPLIERS[0], notes=DEMO_MARKER),
    )
    noor = services.create_supplier(
        db,
        SupplierCreate(**DEMO_SUPPLIERS[1], notes=DEMO_MARKER),
    )
    sapphire = services.create_supplier(
        db,
        SupplierCreate(**DEMO_SUPPLIERS[2], notes=DEMO_MARKER),
    )

    def product(
        supplier_id: int,
        name: str,
        style: str,
        colour: str,
        size: str,
        cost: str,
        price: str,
    ) -> Product:
        return services.create_product(
            db,
            ProductCreate(
                supplier_id=supplier_id,
                name=name,
                description=f"{name} — fictional catalogue sample.",
                style=style,
                colour=colour,
                size=size,
                supplier_cost=Decimal(cost),
                selling_price=Decimal(price),
                notes=DEMO_MARKER,
            ),
        )

    emerald = product(crescent.id, "Emerald Lawn Kurti", "Kurti", "Emerald", "M", "35.00", "75.00")
    maxi = product(crescent.id, "Midnight Chiffon Maxi", "Maxi", "Navy", "L", "48.00", "95.00")
    shirt = product(crescent.id, "Ivory Cotton Shirt", "Shirt", "Ivory", "S", "22.00", "49.00")
    abaya = product(noor.id, "Rose Embroidery Abaya", "Abaya", "Rose", "One size", "55.00", "110.00")
    trousers = product(noor.id, "Teal Linen Trousers", "Trousers", "Teal", "M", "28.00", "58.00")
    kameez = product(noor.id, "Gold Sequin Kameez", "Kameez", "Gold", "L", "60.00", "120.00")
    coral = product(noor.id, "Coral Summer Dress", "Dress", "Coral", "S", "30.00", "65.00")
    blazer = product(sapphire.id, "Black Ponte Blazer", "Blazer", "Black", "M", "40.00", "88.00")
    cardigan = product(sapphire.id, "Cream Knit Cardigan", "Cardigan", "Cream", "L", "32.00", "70.00")
    chambray = product(sapphire.id, "Sky Chambray Shirt", "Shirt", "Sky", "M", "24.00", "52.00")

    customers = [
        services.create_customer(
            db,
            CustomerCreate(
                name=row["name"],
                facebook_name=row["facebook_name"],
                phone=row["phone"],
                notes=DEMO_MARKER,
            ),
        )
        for row in DEMO_CUSTOMERS
    ]
    (
        aisha,
        sara,
        emma,
        nadia,
        lina,
        hannah,
        yasmin,
        priya,
        chloe,
        fatima,
        maya,
        olivia,
    ) = customers

    open_one = _enquiry(db, aisha.id, emerald.id, days_ago=2)
    open_two = _enquiry(db, sara.id, trousers.id, days_ago=4)
    lost_expensive = _enquiry(
        db, nadia.id, kameez.id, days_ago=12, outcome="TOO_EXPENSIVE"
    )
    lost_unavailable = _enquiry(
        db, lina.id, abaya.id, days_ago=14, outcome="SUPPLIER_UNAVAILABLE"
    )
    lost_ghosted = _enquiry(
        db, hannah.id, maxi.id, days_ago=9, outcome="CUSTOMER_GHOSTED"
    )
    lost_size = _enquiry(db, yasmin.id, blazer.id, days_ago=8, outcome="WRONG_SIZE")
    lost_interest = _enquiry(
        db, priya.id, coral.id, days_ago=11, outcome="NOT_INTERESTED"
    )

    enq_confirmed = _enquiry(db, aisha.id, emerald.id, days_ago=18)
    po_confirmed = _preorder_from_enquiry(db, enq_confirmed)

    enq_draft = _enquiry(db, sara.id, maxi.id, days_ago=17)
    po_draft = _preorder_from_enquiry(db, enq_draft)
    _pay(db, po_draft.id, "40.00", reference="BT-4401")

    enq_placed = _enquiry(db, emma.id, shirt.id, days_ago=16)
    po_placed = _preorder_from_enquiry(db, enq_placed)

    enq_so_confirmed = _enquiry(db, nadia.id, emerald.id, days_ago=15)
    po_so_confirmed = _preorder_from_enquiry(db, enq_so_confirmed)

    enq_dispatched = _enquiry(db, lina.id, abaya.id, days_ago=13)
    po_dispatched = _preorder_from_enquiry(db, enq_dispatched)

    enq_arrived = _enquiry(db, hannah.id, trousers.id, days_ago=12)
    po_arrived = _preorder_from_enquiry(db, enq_arrived)

    enq_home = _enquiry(db, yasmin.id, kameez.id, days_ago=20)
    po_home = _preorder_from_enquiry(db, enq_home)
    _pay(db, po_home.id, "120.00", method="REVOLUT", reference="RV-1201")

    enq_regular = _enquiry(db, priya.id, blazer.id, days_ago=19)
    po_regular = _preorder_from_enquiry(db, enq_regular)
    _pay(db, po_regular.id, "88.00", reference="BT-8801")

    enq_registered = _enquiry(db, chloe.id, cardigan.id, days_ago=19)
    po_registered = _preorder_from_enquiry(db, enq_registered)
    _pay(db, po_registered.id, "70.00", reference="BT-7001")

    enq_excess_a = _enquiry(db, fatima.id, coral.id, quantity=2, days_ago=21)
    po_excess_a = _preorder_from_enquiry(db, enq_excess_a)
    enq_excess_b = _enquiry(db, maya.id, coral.id, quantity=2, days_ago=21)
    po_excess_b = _preorder_from_enquiry(db, enq_excess_b)

    enq_short_a = _enquiry(db, olivia.id, chambray.id, quantity=2, days_ago=22)
    po_short_a = _preorder_from_enquiry(db, enq_short_a)
    enq_short_b = _enquiry(db, sara.id, chambray.id, quantity=2, days_ago=22)
    po_short_b = _preorder_from_enquiry(db, enq_short_b)
    enq_short_c = _enquiry(db, emma.id, chambray.id, quantity=1, days_ago=22)
    po_short_c = _preorder_from_enquiry(db, enq_short_c)

    enq_cancelled = _enquiry(db, lina.id, shirt.id, days_ago=7)
    po_cancelled = _preorder_from_enquiry(db, enq_cancelled)
    services.transition_preorder(
        db, po_cancelled.id, PreorderTransition(status="CANCELLED")
    )

    enq_unavailable = _enquiry(db, fatima.id, maxi.id, days_ago=5)
    po_unavailable = _preorder_from_enquiry(db, enq_unavailable)
    services.transition_preorder(
        db, po_unavailable.id, PreorderTransition(status="SUPPLIER_UNAVAILABLE")
    )

    walk_in = services.create_preorder(
        db,
        PreorderCreate(
            customer_id=olivia.id,
            product_id=shirt.id,
            quantity=1,
            notes=f"{DEMO_MARKER} · walk-in for Olivia Brogan, Ivory Cotton Shirt",
        ),
    )

    _draft(db, crescent.id, [po_draft.id])
    _advance(db, _draft(db, crescent.id, [po_placed.id]).id, "PLACED")
    _advance(db, _draft(db, crescent.id, [po_so_confirmed.id]).id, "CONFIRMED")
    _advance(db, _draft(db, noor.id, [po_dispatched.id]).id, "DISPATCHED")
    _advance(db, _draft(db, noor.id, [po_arrived.id]).id, "ARRIVED")

    home_order = _advance(db, _draft(db, noor.id, [po_home.id]).id, "ARRIVED")
    _reconcile_all(
        db, home_order, {line.id: line.quantity for line in home_order.lines}
    )
    services.transition_preorder(
        db, po_home.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )
    services.fulfil_preorder(
        db, po_home.id, FulfilmentCreate(method="HOME_COLLECTION", notes=DEMO_MARKER)
    )

    regular_order = _advance(db, _draft(db, sapphire.id, [po_regular.id]).id, "ARRIVED")
    _reconcile_all(
        db, regular_order, {line.id: line.quantity for line in regular_order.lines}
    )
    services.transition_preorder(
        db, po_regular.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )
    services.fulfil_preorder(
        db,
        po_regular.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address="14 Willow Lane, Galway, H91 0000",
            postage_cost=Decimal("4.50"),
            notes=DEMO_MARKER,
        ),
    )

    registered_order = _advance(
        db, _draft(db, sapphire.id, [po_registered.id]).id, "ARRIVED"
    )
    _reconcile_all(
        db,
        registered_order,
        {line.id: line.quantity for line in registered_order.lines},
    )
    services.transition_preorder(
        db, po_registered.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )
    services.fulfil_preorder(
        db,
        po_registered.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGISTERED",
            delivery_address="8 Harbour Walk, Cork, T12 0000",
            postage_cost=Decimal("8.00"),
            tracking_reference="DEMO-REG-1001",
            notes=DEMO_MARKER,
        ),
    )

    ready_enq = _enquiry(db, maya.id, blazer.id, days_ago=18)
    po_ready = _preorder_from_enquiry(db, ready_enq)
    ready_order = _advance(db, _draft(db, sapphire.id, [po_ready.id]).id, "ARRIVED")
    _reconcile_all(
        db, ready_order, {line.id: line.quantity for line in ready_order.lines}
    )
    services.transition_preorder(
        db, po_ready.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )

    excess_order = _advance(
        db, _draft(db, noor.id, [po_excess_a.id, po_excess_b.id]).id, "ARRIVED"
    )
    extra = {line.id: line.quantity + 1 for line in excess_order.lines}
    _reconcile_all(db, excess_order, extra)

    short_order = _advance(
        db,
        _draft(db, sapphire.id, [po_short_a.id, po_short_b.id, po_short_c.id]).id,
        "ARRIVED",
    )
    short_received = {line.id: 4 for line in short_order.lines}
    _reconcile_all(db, short_order, short_received)

    arrived_customer_enq = _enquiry(db, chloe.id, emerald.id, days_ago=16)
    po_arrived_customer = _preorder_from_enquiry(db, arrived_customer_enq)
    arrived_customer_order = _advance(
        db, _draft(db, crescent.id, [po_arrived_customer.id]).id, "ARRIVED"
    )
    _reconcile_all(
        db,
        arrived_customer_order,
        {line.id: line.quantity for line in arrived_customer_order.lines},
    )

    _ = (
        open_one,
        open_two,
        lost_expensive,
        lost_unavailable,
        lost_ghosted,
        lost_size,
        lost_interest,
        po_confirmed,
        walk_in,
        po_arrived,
        po_short_c,
    )

    return {
        "suppliers": len(services.list_suppliers(db)),
        "products": len(services.list_products(db)),
        "customers": len(services.list_customers(db)),
        "enquiries": len(services.list_enquiries(db)),
        "preorders": len(services.list_preorders(db)),
        "supplier_orders": len(services.list_supplier_orders(db)),
        "inventory_lots": len(services.list_inventory_lots(db)),
    }


def _resolve_url() -> str | None:
    raw = os.environ.get("DEMO_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        return None
    return normalize_database_url(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a synthetic local demo database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe application tables on the guarded demo/test database, then seed.",
    )
    args = parser.parse_args(argv)

    try:
        url = _resolve_url()
        assert_demo_seed_allowed(
            allow_flag=os.environ.get("ALLOW_DEMO_SEED"),
            database_url=url,
        )
    except UnsafeDemoTargetError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.reset:
        print(
            "Refusing to seed without --reset. Re-run with --reset on a guarded "
            "local demo/test database.",
            file=sys.stderr,
        )
        return 2

    assert url is not None
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        _wipe_application_tables(db)
        summary = seed_demo_data(db)
    finally:
        db.close()
        engine.dispose()

    print("Synthetic demo data loaded:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
