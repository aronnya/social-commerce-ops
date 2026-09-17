from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import InventoryLot
from app.schemas import (
    CustomerCreate,
    PaymentCreate,
    PreorderCreate,
    PreorderTransition,
    ProductCreate,
    ReconciliationLineInput,
    SupplierCreate,
    SupplierOrderReconcile,
    SupplierOrderTransition,
)
from app.services import (
    SUPPLIER_ORDER_ALLOWED_TRANSITIONS,
    ConflictError,
    NotFoundError,
    create_customer,
    create_payment,
    create_preorder,
    create_product,
    create_supplier,
    delete_product,
    generate_supplier_order_draft,
    get_inventory_lot,
    get_preorder,
    get_supplier_order,
    list_inventory_lots,
    list_payments,
    place_supplier_order,
    reconcile_supplier_order,
    transition_preorder,
    transition_supplier_order,
)


def _catalogue(db: Session, *, suffix: str = "Recon"):
    supplier = create_supplier(db, SupplierCreate(name=f"Demo {suffix} Supplier"))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name=f"Demo {suffix} Dress",
            supplier_cost=Decimal("40.00"),
            selling_price=Decimal("85.00"),
        ),
    )
    customer = create_customer(db, CustomerCreate(name=f"Demo {suffix} Customer"))
    return supplier, product, customer


def _preorder(db: Session, customer_id: int, product_id: int, quantity: int):
    return create_preorder(
        db,
        PreorderCreate(
            customer_id=customer_id, product_id=product_id, quantity=quantity
        ),
    )


def _arrive_order(db: Session, order_id: int):
    order = place_supplier_order(db, order_id)
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        order = transition_supplier_order(
            db, order.id, SupplierOrderTransition(status=status)
        )
    return order


def _arrived_from_preorders(db: Session, supplier_id: int, preorder_ids: list[int]):
    draft = generate_supplier_order_draft(db, supplier_id, preorder_ids)
    return _arrive_order(db, draft.id)


def _reconcile(
    db: Session,
    order,
    received_by_line: dict[int, int] | None = None,
    *,
    notes: str | None = None,
    arrived_ids_by_line: dict[int, list[int] | None] | None = None,
):
    lines = []
    for line in order.lines:
        received = (
            received_by_line[line.id]
            if received_by_line is not None
            else line.quantity
        )
        payload = ReconciliationLineInput(line_id=line.id, received_quantity=received)
        if arrived_ids_by_line is not None and line.id in arrived_ids_by_line:
            payload = ReconciliationLineInput(
                line_id=line.id,
                received_quantity=received,
                arrived_preorder_ids=arrived_ids_by_line[line.id],
            )
        lines.append(payload)
    return reconcile_supplier_order(
        db,
        order.id,
        SupplierOrderReconcile(lines=lines, reconciliation_notes=notes),
    )


def test_exact_reconciliation(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Exact")
    preorder = _preorder(db_session, customer.id, product.id, 2)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    line = order.lines[0]
    reconciled = _reconcile(db_session, order, {line.id: 2})
    assert reconciled.status == "RECONCILED"
    assert reconciled.reconciled_at is not None
    assert reconciled.lines[0].received_quantity == 2
    assert reconciled.lines[0].quantity == 2
    assert get_preorder(db_session, preorder.id).status == "ARRIVED"
    assert list_inventory_lots(db_session) == []


def test_shortage_fills_complete_fifo_preorders_only(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Shortage")
    first = _preorder(db_session, customer.id, product.id, 2)
    second = _preorder(db_session, customer.id, product.id, 2)
    third = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(
        db_session, supplier.id, [first.id, second.id, third.id]
    )
    line = order.lines[0]
    _reconcile(db_session, order, {line.id: 4})
    assert get_preorder(db_session, first.id).status == "ARRIVED"
    assert get_preorder(db_session, second.id).status == "ARRIVED"
    assert get_preorder(db_session, third.id).status == "ORDERED_FROM_SUPPLIER"
    assert list_inventory_lots(db_session) == []


def test_fifo_stop_does_not_skip_older_larger_preorder(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="FifoStop")
    older = _preorder(db_session, customer.id, product.id, 2)
    newer = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [older.id, newer.id])
    line = order.lines[0]
    reconciled = _reconcile(db_session, order, {line.id: 1})
    assert get_preorder(db_session, older.id).status == "ORDERED_FROM_SUPPLIER"
    assert get_preorder(db_session, newer.id).status == "ORDERED_FROM_SUPPLIER"
    lots = list_inventory_lots(db_session)
    assert len(lots) == 1
    assert lots[0].quantity_on_hand == 1
    assert lots[0].product_id == product.id
    assert lots[0].supplier_order_line_id == line.id
    assert reconciled.status == "RECONCILED"


def test_partial_leftover_becomes_inventory_lot(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Leftover")
    first = _preorder(db_session, customer.id, product.id, 2)
    second = _preorder(db_session, customer.id, product.id, 2)
    order = _arrived_from_preorders(db_session, supplier.id, [first.id, second.id])
    line = order.lines[0]
    _reconcile(db_session, order, {line.id: 3})
    assert get_preorder(db_session, first.id).status == "ARRIVED"
    assert get_preorder(db_session, second.id).status == "ORDERED_FROM_SUPPLIER"
    lots = list_inventory_lots(db_session)
    assert len(lots) == 1
    assert lots[0].quantity_on_hand == 1


def test_over_delivery_arrives_fitting_preorders_and_lots_remainder(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Over")
    first = _preorder(db_session, customer.id, product.id, 2)
    second = _preorder(db_session, customer.id, product.id, 2)
    order = _arrived_from_preorders(db_session, supplier.id, [first.id, second.id])
    line = order.lines[0]
    _reconcile(db_session, order, {line.id: 5})
    assert get_preorder(db_session, first.id).status == "ARRIVED"
    assert get_preorder(db_session, second.id).status == "ARRIVED"
    lots = list_inventory_lots(db_session)
    assert len(lots) == 1
    assert lots[0].quantity_on_hand == 1


def test_zero_receipt_reconciles_without_lot_or_preorder_advance(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Zero")
    preorder = _preorder(db_session, customer.id, product.id, 2)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    line = order.lines[0]
    reconciled = _reconcile(db_session, order, {line.id: 0})
    assert reconciled.status == "RECONCILED"
    assert reconciled.lines[0].received_quantity == 0
    assert get_preorder(db_session, preorder.id).status == "ORDERED_FROM_SUPPLIER"
    assert list_inventory_lots(db_session) == []


def test_explicit_override_valid_subset_and_remainder(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Override")
    first = _preorder(db_session, customer.id, product.id, 2)
    second = _preorder(db_session, customer.id, product.id, 2)
    third = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(
        db_session, supplier.id, [first.id, second.id, third.id]
    )
    line = order.lines[0]
    reconciled = _reconcile(
        db_session,
        order,
        {line.id: 3},
        arrived_ids_by_line={line.id: [third.id]},
    )
    assert get_preorder(db_session, first.id).status == "ORDERED_FROM_SUPPLIER"
    assert get_preorder(db_session, second.id).status == "ORDERED_FROM_SUPPLIER"
    assert get_preorder(db_session, third.id).status == "ARRIVED"
    lots = list_inventory_lots(db_session)
    assert len(lots) == 1
    assert lots[0].quantity_on_hand == 2
    assert reconciled.status == "RECONCILED"


def test_empty_arrived_preorder_ids_selects_none_and_lots_remainder(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="EmptyIds")
    first = _preorder(db_session, customer.id, product.id, 2)
    second = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [first.id, second.id])
    line = order.lines[0]
    reconciled = _reconcile(
        db_session,
        order,
        {line.id: 3},
        arrived_ids_by_line={line.id: []},
    )
    assert get_preorder(db_session, first.id).status == "ORDERED_FROM_SUPPLIER"
    assert get_preorder(db_session, second.id).status == "ORDERED_FROM_SUPPLIER"
    lots = list_inventory_lots(db_session)
    assert len(lots) == 1
    assert lots[0].quantity_on_hand == 3
    assert lots[0].supplier_order_line_id == line.id
    assert reconciled.status == "RECONCILED"


def test_explicit_override_unallocated_preorder_conflicts(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Unalloc")
    allocated = _preorder(db_session, customer.id, product.id, 2)
    other_product = create_product(
        db_session,
        ProductCreate(supplier_id=supplier.id, name="Demo Unalloc Other"),
    )
    other = _preorder(db_session, customer.id, other_product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [allocated.id])
    line = order.lines[0]
    with pytest.raises(ConflictError):
        _reconcile(
            db_session,
            order,
            {line.id: 2},
            arrived_ids_by_line={line.id: [other.id]},
        )
    still = get_supplier_order(db_session, order.id)
    assert still.status == "ARRIVED"
    assert still.lines[0].received_quantity is None


def test_explicit_override_selected_quantity_exceeds_received(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="TooMuch")
    preorder = _preorder(db_session, customer.id, product.id, 2)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    line = order.lines[0]
    with pytest.raises(ConflictError):
        _reconcile(
            db_session,
            order,
            {line.id: 1},
            arrived_ids_by_line={line.id: [preorder.id]},
        )
    assert get_supplier_order(db_session, order.id).status == "ARRIVED"
    assert get_preorder(db_session, preorder.id).status == "ORDERED_FROM_SUPPLIER"


def test_order_not_arrived_conflicts(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="NotArrived")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    placed = place_supplier_order(db_session, draft.id)
    with pytest.raises(ConflictError):
        _reconcile(db_session, placed, {placed.lines[0].id: 1})


def test_already_reconciled_conflicts(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Twice")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    _reconcile(db_session, order, {order.lines[0].id: 1})
    with pytest.raises(ConflictError):
        _reconcile(db_session, order, {order.lines[0].id: 1})


def test_missing_line_in_payload_conflicts(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="MissingLine")
    first_product = product
    second_product = create_product(
        db_session,
        ProductCreate(supplier_id=supplier.id, name="Demo MissingLine Two"),
    )
    a = _preorder(db_session, customer.id, first_product.id, 1)
    b = _preorder(db_session, customer.id, second_product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [a.id, b.id])
    with pytest.raises(ConflictError):
        reconcile_supplier_order(
            db_session,
            order.id,
            SupplierOrderReconcile(
                lines=[
                    ReconciliationLineInput(
                        line_id=order.lines[0].id, received_quantity=1
                    )
                ]
            ),
        )
    assert get_supplier_order(db_session, order.id).status == "ARRIVED"


def test_unknown_line_not_found(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="UnknownLine")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    with pytest.raises(NotFoundError):
        reconcile_supplier_order(
            db_session,
            order.id,
            SupplierOrderReconcile(
                lines=[ReconciliationLineInput(line_id=999999, received_quantity=1)]
            ),
        )


def test_foreign_line_conflicts(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="ForeignA")
    other_supplier, other_product, other_customer = _catalogue(
        db_session, suffix="ForeignB"
    )
    a = _preorder(db_session, customer.id, product.id, 1)
    b = _preorder(db_session, other_customer.id, other_product.id, 1)
    order_a = _arrived_from_preorders(db_session, supplier.id, [a.id])
    order_b = _arrived_from_preorders(db_session, other_supplier.id, [b.id])
    with pytest.raises(ConflictError):
        reconcile_supplier_order(
            db_session,
            order_a.id,
            SupplierOrderReconcile(
                lines=[
                    ReconciliationLineInput(
                        line_id=order_b.lines[0].id, received_quantity=1
                    )
                ]
            ),
        )


def test_selected_preorder_wrong_status_conflicts(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="WrongStatus")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    transition_preorder(
        db_session, preorder.id, PreorderTransition(status="CANCELLED")
    )
    line = order.lines[0]
    with pytest.raises(ConflictError):
        _reconcile(
            db_session,
            order,
            {line.id: 1},
            arrived_ids_by_line={line.id: [preorder.id]},
        )
    assert get_supplier_order(db_session, order.id).status == "ARRIVED"


def test_payments_unchanged_and_ready_for_customer_not_automatic(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Payments")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    payment = create_payment(
        db_session,
        preorder.id,
        PaymentCreate(amount=Decimal("20.00"), method="REVOLUT"),
    )
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    _reconcile(db_session, order, {order.lines[0].id: 1})
    arrived = get_preorder(db_session, preorder.id)
    assert arrived.status == "ARRIVED"
    payments = list_payments(db_session, preorder.id)
    assert len(payments) == 1
    assert payments[0].id == payment.id
    assert payments[0].amount == Decimal("20.00")
    with pytest.raises(ValidationError):
        PreorderTransition(status="FULFILLED")
    ready = transition_preorder(
        db_session, preorder.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )
    assert ready.status == "READY_FOR_CUSTOMER"


def test_generic_supplier_order_arrived_to_reconciled_blocked(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="GenericSO")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    assert SUPPLIER_ORDER_ALLOWED_TRANSITIONS["ARRIVED"] == frozenset()
    with pytest.raises(ValidationError):
        SupplierOrderTransition(status="RECONCILED")
    with pytest.raises(ConflictError):
        transition_supplier_order(
            db_session, order.id, SupplierOrderTransition(status="ARRIVED")
        )
    assert get_supplier_order(db_session, order.id).status == "ARRIVED"


def test_generic_preorder_ordered_to_arrived_blocked(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="GenericPO")
    preorder = _preorder(db_session, customer.id, product.id, 1)
    _arrived_from_preorders(db_session, supplier.id, [preorder.id])
    with pytest.raises(ConflictError):
        transition_preorder(db_session, preorder.id, PreorderTransition(status="ARRIVED"))


def test_product_delete_blocked_if_inventory_lot_exists(db_session: Session) -> None:
    supplier = create_supplier(db_session, SupplierCreate(name="Demo Lot Delete Supplier"))
    product = create_product(
        db_session,
        ProductCreate(supplier_id=supplier.id, name="Demo Lot Delete Dress"),
    )
    db_session.add(
        InventoryLot(product_id=product.id, quantity_on_hand=1, supplier_order_line_id=None)
    )
    db_session.commit()
    with pytest.raises(ConflictError):
        delete_product(db_session, product.id)


def test_failed_line_rolls_back_valid_line(db_session: Session) -> None:
    supplier, product_a, customer = _catalogue(db_session, suffix="RollbackA")
    product_b = create_product(
        db_session,
        ProductCreate(
            supplier_id=supplier.id,
            name="Demo RollbackB Dress",
            supplier_cost=Decimal("10.00"),
            selling_price=Decimal("20.00"),
        ),
    )
    a = _preorder(db_session, customer.id, product_a.id, 2)
    b = _preorder(db_session, customer.id, product_b.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [a.id, b.id])
    line_a = next(line for line in order.lines if line.product_id == product_a.id)
    line_b = next(line for line in order.lines if line.product_id == product_b.id)
    with pytest.raises(ConflictError):
        reconcile_supplier_order(
            db_session,
            order.id,
            SupplierOrderReconcile(
                lines=[
                    ReconciliationLineInput(line_id=line_a.id, received_quantity=2),
                    ReconciliationLineInput(
                        line_id=line_b.id,
                        received_quantity=1,
                        arrived_preorder_ids=[a.id],
                    ),
                ]
            ),
        )
    still = get_supplier_order(db_session, order.id)
    assert still.status == "ARRIVED"
    assert still.reconciled_at is None
    by_id = {line.id: line for line in still.lines}
    assert by_id[line_a.id].received_quantity is None
    assert by_id[line_b.id].received_quantity is None
    assert get_preorder(db_session, a.id).status == "ORDERED_FROM_SUPPLIER"
    assert get_preorder(db_session, b.id).status == "ORDERED_FROM_SUPPLIER"
    assert list_inventory_lots(db_session) == []


def test_list_and_get_inventory_lots(db_session: Session) -> None:
    supplier, product_a, customer = _catalogue(db_session, suffix="LotsA")
    product_b = create_product(
        db_session,
        ProductCreate(supplier_id=supplier.id, name="Demo LotsB Dress"),
    )
    a = _preorder(db_session, customer.id, product_a.id, 1)
    b = _preorder(db_session, customer.id, product_b.id, 1)
    order = _arrived_from_preorders(db_session, supplier.id, [a.id, b.id])
    line_a = next(line for line in order.lines if line.product_id == product_a.id)
    line_b = next(line for line in order.lines if line.product_id == product_b.id)
    _reconcile(db_session, order, {line_a.id: 2, line_b.id: 3})
    lots = list_inventory_lots(db_session)
    assert len(lots) == 2
    filtered = list_inventory_lots(db_session, product_id=product_a.id)
    assert len(filtered) == 1
    assert filtered[0].product_id == product_a.id
    assert filtered[0].quantity_on_hand == 1
    found = get_inventory_lot(db_session, filtered[0].id)
    assert found.id == filtered[0].id
    with pytest.raises(NotFoundError):
        get_inventory_lot(db_session, 999999)


def test_missing_supplier_order_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        reconcile_supplier_order(
            db_session,
            999999,
            SupplierOrderReconcile(
                lines=[ReconciliationLineInput(line_id=1, received_quantity=0)]
            ),
        )
