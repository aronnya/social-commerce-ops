from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import SupplierOrder
from app.schemas import (
    CustomerCreate,
    PaymentCreate,
    PreorderCreate,
    PreorderTransition,
    PreorderUpdate,
    ProductCreate,
    ProductUpdate,
    SupplierCreate,
    SupplierOrderTransition,
    SupplierOrderUpdate,
)
from app.services import (
    ConflictError,
    NotFoundError,
    create_customer,
    create_payment,
    create_preorder,
    create_product,
    create_supplier,
    delete_supplier,
    delete_supplier_order_draft,
    generate_supplier_order_draft,
    get_preorder,
    get_product,
    list_payments,
    list_supplier_orders,
    place_supplier_order,
    transition_preorder,
    transition_supplier_order,
    update_preorder,
    update_product,
    update_supplier_order,
)


def _supplier_catalogue(
    db: Session,
    *,
    supplier_name: str = "Demo SO Supplier",
    product_name: str = "Demo SO Dress",
    supplier_cost: Decimal | None = Decimal("40.00"),
    selling_price: Decimal | None = Decimal("85.00"),
):
    supplier = create_supplier(db, SupplierCreate(name=supplier_name))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name=product_name,
            supplier_cost=supplier_cost,
            selling_price=selling_price,
        ),
    )
    customer = create_customer(db, CustomerCreate(name=f"Demo SO Customer {supplier_name}"))
    return supplier, product, customer


def _preorder(db: Session, customer_id: int, product_id: int, quantity: int = 1):
    return create_preorder(
        db,
        PreorderCreate(
            customer_id=customer_id, product_id=product_id, quantity=quantity
        ),
    )


def test_generate_draft_missing_supplier(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        generate_supplier_order_draft(db_session, 999999, None)


def test_generate_draft_missing_preorder(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    _preorder(db_session, customer.id, product.id)
    with pytest.raises(NotFoundError):
        generate_supplier_order_draft(db_session, supplier.id, [999999])


def test_generate_draft_empty_eligible_set(db_session: Session) -> None:
    supplier, _product, _customer = _supplier_catalogue(db_session)
    with pytest.raises(ConflictError):
        generate_supplier_order_draft(db_session, supplier.id, None)


def test_generate_draft_one_preorder(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id, quantity=2)
    order = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    assert order.status == "DRAFT"
    assert order.placed_at is None
    assert len(order.lines) == 1
    assert order.lines[0].product_id == product.id
    assert order.lines[0].quantity == 2
    assert order.lines[0].unit_cost == Decimal("40.00")
    assert len(order.lines[0].allocations) == 1
    assert order.lines[0].allocations[0].preorder_id == preorder.id
    assert order.lines[0].allocations[0].quantity == 2
    assert get_preorder(db_session, preorder.id).status == "CONFIRMED"


def test_generate_draft_consolidates_same_product(db_session: Session) -> None:
    supplier, product_x, customer = _supplier_catalogue(db_session)
    product_y = create_product(
        db_session,
        ProductCreate(
            supplier_id=supplier.id,
            name="Demo SO Dress Y",
            supplier_cost=Decimal("15.00"),
            selling_price=Decimal("50.00"),
        ),
    )
    a = _preorder(db_session, customer.id, product_x.id, quantity=2)
    b = _preorder(db_session, customer.id, product_x.id, quantity=1)
    c = _preorder(db_session, customer.id, product_y.id, quantity=1)
    order = generate_supplier_order_draft(
        db_session, supplier.id, [a.id, b.id, c.id]
    )
    lines = {line.product_id: line for line in order.lines}
    assert lines[product_x.id].quantity == 3
    assert {alloc.preorder_id for alloc in lines[product_x.id].allocations} == {a.id, b.id}
    assert lines[product_y.id].quantity == 1
    assert lines[product_y.id].allocations[0].preorder_id == c.id
    assert get_preorder(db_session, a.id).status == "CONFIRMED"
    assert get_preorder(db_session, b.id).status == "CONFIRMED"
    assert get_preorder(db_session, c.id).status == "CONFIRMED"


def test_generate_draft_mixed_suppliers_conflicts(db_session: Session) -> None:
    supplier_a, product_a, customer_a = _supplier_catalogue(db_session, supplier_name="SO A")
    _supplier_b, product_b, customer_b = _supplier_catalogue(db_session, supplier_name="SO B")
    pre_a = _preorder(db_session, customer_a.id, product_a.id)
    pre_b = _preorder(db_session, customer_b.id, product_b.id)
    with pytest.raises(ConflictError):
        generate_supplier_order_draft(db_session, supplier_a.id, [pre_a.id, pre_b.id])


def test_generate_draft_non_confirmed_conflicts(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id)
    transition_preorder(db_session, preorder.id, PreorderTransition(status="CANCELLED"))
    with pytest.raises(ConflictError):
        generate_supplier_order_draft(db_session, supplier.id, [preorder.id])


def test_generate_draft_already_allocated_conflicts(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id)
    generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    with pytest.raises(ConflictError):
        generate_supplier_order_draft(db_session, supplier.id, [preorder.id])


def test_generate_draft_omitted_ids_selects_eligible_only(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session, supplier_name="SO Main")
    other, other_product, other_customer = _supplier_catalogue(
        db_session, supplier_name="SO Other"
    )
    mine = _preorder(db_session, customer.id, product.id, quantity=2)
    _preorder(db_session, other_customer.id, other_product.id)
    cancelled = _preorder(db_session, customer.id, product.id)
    transition_preorder(db_session, cancelled.id, PreorderTransition(status="CANCELLED"))
    order = generate_supplier_order_draft(db_session, supplier.id, None)
    alloc_ids = {
        allocation.preorder_id
        for line in order.lines
        for allocation in line.allocations
    }
    assert alloc_ids == {mine.id}
    listed = list_supplier_orders(db_session, supplier_id=supplier.id, status="DRAFT")
    assert [item.id for item in listed] == [order.id]


def test_place_supplier_order_success(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id, quantity=2)
    payment = create_payment(
        db_session,
        preorder.id,
        PaymentCreate(amount=Decimal("10.00"), method="REVOLUT"),
    )
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    placed = place_supplier_order(db_session, draft.id)
    assert placed.status == "PLACED"
    assert placed.placed_at is not None
    assert get_preorder(db_session, preorder.id).status == "ORDERED_FROM_SUPPLIER"
    payments = list_payments(db_session, preorder.id)
    assert [item.id for item in payments] == [payment.id]
    assert payments[0].amount == Decimal("10.00")
    with pytest.raises(ConflictError):
        place_supplier_order(db_session, placed.id)


def test_place_empty_draft_conflicts(db_session: Session) -> None:
    supplier, _product, _customer = _supplier_catalogue(db_session)
    empty = SupplierOrder(supplier_id=supplier.id, status="DRAFT")
    db_session.add(empty)
    db_session.commit()
    with pytest.raises(ConflictError):
        place_supplier_order(db_session, empty.id)


def test_place_line_quantity_mismatch_conflicts(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id, quantity=2)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    draft.lines[0].quantity = 99
    db_session.commit()
    with pytest.raises(ConflictError):
        place_supplier_order(db_session, draft.id)


def test_supplier_order_status_transitions(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    with pytest.raises(ConflictError):
        transition_supplier_order(
            db_session, draft.id, SupplierOrderTransition(status="CONFIRMED")
        )
    placed = place_supplier_order(db_session, draft.id)
    confirmed = transition_supplier_order(
        db_session, placed.id, SupplierOrderTransition(status="CONFIRMED")
    )
    assert confirmed.status == "CONFIRMED"
    dispatched = transition_supplier_order(
        db_session, confirmed.id, SupplierOrderTransition(status="DISPATCHED")
    )
    assert dispatched.status == "DISPATCHED"
    arrived = transition_supplier_order(
        db_session, dispatched.id, SupplierOrderTransition(status="ARRIVED")
    )
    assert arrived.status == "ARRIVED"
    reconciled = transition_supplier_order(
        db_session, arrived.id, SupplierOrderTransition(status="RECONCILED")
    )
    assert reconciled.status == "RECONCILED"
    assert get_preorder(db_session, preorder.id).status == "ORDERED_FROM_SUPPLIER"
    with pytest.raises(ConflictError):
        transition_supplier_order(
            db_session, reconciled.id, SupplierOrderTransition(status="ARRIVED")
        )
    with pytest.raises(ConflictError):
        transition_supplier_order(
            db_session, reconciled.id, SupplierOrderTransition(status="RECONCILED")
        )


def test_delete_draft_releases_preorder(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    delete_supplier_order_draft(db_session, draft.id)
    assert get_preorder(db_session, preorder.id).status == "CONFIRMED"
    again = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    assert again.status == "DRAFT"
    placed = place_supplier_order(db_session, again.id)
    with pytest.raises(ConflictError):
        delete_supplier_order_draft(db_session, placed.id)


def test_update_supplier_order_notes(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    updated = update_supplier_order(
        db_session, draft.id, SupplierOrderUpdate(notes="check sizes")
    )
    assert updated.notes == "check sizes"
    assert updated.status == "DRAFT"


def test_allocated_preorder_quantity_frozen_notes_ok(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    preorder = _preorder(db_session, customer.id, product.id, quantity=2)
    generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    with pytest.raises(ConflictError):
        update_preorder(db_session, preorder.id, PreorderUpdate(quantity=3))
    notes = update_preorder(
        db_session, preorder.id, PreorderUpdate(notes="still confirmed")
    )
    assert notes.notes == "still confirmed"
    assert notes.status == "CONFIRMED"
    priced = update_preorder(
        db_session, preorder.id, PreorderUpdate(agreed_price=Decimal("80.00"))
    )
    assert priced.agreed_price == Decimal("80.00")
    with pytest.raises(ConflictError):
        transition_preorder(
            db_session, preorder.id, PreorderTransition(status="ORDERED_FROM_SUPPLIER")
        )


def test_product_supplier_change_blocked_by_line(db_session: Session) -> None:
    supplier, product, customer = _supplier_catalogue(db_session)
    other = create_supplier(db_session, SupplierCreate(name="Demo Other SO Supplier"))
    preorder = _preorder(db_session, customer.id, product.id)
    generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    with pytest.raises(ConflictError):
        update_product(db_session, product.id, ProductUpdate(supplier_id=other.id))
    renamed = update_product(
        db_session, product.id, ProductUpdate(name="Demo SO Dress Renamed")
    )
    assert renamed.name == "Demo SO Dress Renamed"
    assert renamed.supplier_id == supplier.id


def test_delete_supplier_with_order_conflicts(db_session: Session) -> None:
    supplier = create_supplier(db_session, SupplierCreate(name="Demo Empty SO Supplier"))
    order = SupplierOrder(supplier_id=supplier.id, status="DRAFT")
    db_session.add(order)
    db_session.commit()
    with pytest.raises(ConflictError):
        delete_supplier(db_session, supplier.id)
