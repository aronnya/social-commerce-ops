from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InventoryLot, Product, SupplierOrder, SupplierOrderLine
from app.schemas import CustomerCreate, PreorderCreate, ProductCreate, SupplierCreate
from app.services import (
    create_customer,
    create_preorder,
    create_product,
    create_supplier,
    generate_supplier_order_draft,
)


def test_models_import_and_relationships() -> None:
    assert "received_quantity" in SupplierOrderLine.__table__.c
    assert SupplierOrderLine.__table__.c.received_quantity.nullable is True
    assert "quantity_on_hand" not in Product.__table__.c
    assert "inventory_lots" in Product.__mapper__.relationships
    assert "inventory_lot" in SupplierOrderLine.__mapper__.relationships
    assert "product" in InventoryLot.__mapper__.relationships
    assert "supplier_order_line" in InventoryLot.__mapper__.relationships
    assert "reconciled_at" in SupplierOrder.__table__.c
    assert "reconciliation_notes" in SupplierOrder.__table__.c


def _draft_line(db: Session) -> SupplierOrderLine:
    supplier = create_supplier(db, SupplierCreate(name="Demo Inventory Supplier"))
    product = create_product(
        db,
        ProductCreate(supplier_id=supplier.id, name="Demo Inventory Dress"),
    )
    customer = create_customer(db, CustomerCreate(name="Demo Inventory Customer"))
    preorder = create_preorder(
        db,
        PreorderCreate(customer_id=customer.id, product_id=product.id, quantity=2),
    )
    order = generate_supplier_order_draft(db, supplier.id, [preorder.id])
    return order.lines[0]


def test_received_quantity_nullable_zero_and_over_receipt(db_session: Session) -> None:
    line = _draft_line(db_session)
    assert line.received_quantity is None
    assert line.quantity == 2
    line.received_quantity = 0
    db_session.commit()
    db_session.refresh(line)
    assert line.received_quantity == 0
    line.received_quantity = 5
    db_session.commit()
    db_session.refresh(line)
    assert line.received_quantity == 5
    assert line.quantity == 2


def test_negative_received_quantity_rejected(db_session: Session) -> None:
    line = _draft_line(db_session)
    line.received_quantity = -1
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()


def test_inventory_lot_quantity_and_line_uniqueness(db_session: Session) -> None:
    line = _draft_line(db_session)
    lot = InventoryLot(
        product_id=line.product_id,
        quantity_on_hand=1,
        supplier_order_line_id=line.id,
    )
    db_session.add(lot)
    db_session.commit()
    db_session.refresh(lot)
    assert lot.quantity_on_hand == 1
    assert line.inventory_lot.id == lot.id
    assert lot.supplier_order_line.id == line.id

    duplicate = InventoryLot(
        product_id=line.product_id,
        quantity_on_hand=0,
        supplier_order_line_id=line.id,
    )
    db_session.add(duplicate)
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()

    negative = InventoryLot(
        product_id=line.product_id,
        quantity_on_hand=-1,
        supplier_order_line_id=None,
    )
    db_session.add(negative)
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()
