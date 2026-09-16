from decimal import Decimal

from sqlalchemy.orm import Session

from app.schemas import (
    CustomerCreate,
    EnquiryCreate,
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
    create_customer,
    create_enquiry,
    create_payment,
    create_preorder,
    create_product,
    create_supplier,
    generate_supplier_order_draft,
    list_attention,
    place_supplier_order,
    reconcile_supplier_order,
    transition_preorder,
    transition_supplier_order,
)


def _catalogue(db: Session, *, suffix: str):
    supplier = create_supplier(db, SupplierCreate(name=f"Demo Attention Supplier {suffix}"))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name=f"Demo Attention Dress {suffix}",
            supplier_cost=Decimal("40.00"),
            selling_price=Decimal("85.00"),
        ),
    )
    customer = create_customer(db, CustomerCreate(name=f"Demo Attention Customer {suffix}"))
    return supplier, product, customer


def _preorder(db: Session, customer_id: int, product_id: int, quantity: int = 1, **extra):
    return create_preorder(
        db,
        PreorderCreate(
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            **extra,
        ),
    )


def _arrive_order(db: Session, order_id: int):
    place_supplier_order(db, order_id)
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        transition_supplier_order(db, order_id, SupplierOrderTransition(status=status))


def _types(queue) -> list[str]:
    return [item.type for item in queue.items]


def test_empty_queue(db_session: Session) -> None:
    queue = list_attention(db_session)
    assert queue.items == []
    assert queue.counts.model_dump() == {
        "preorder_overpaid": 0,
        "supplier_order_needs_reconciliation": 0,
        "preorder_needs_customer_ready": 0,
        "preorder_needs_fulfilment": 0,
        "supplier_order_draft_needs_placement": 0,
        "preorder_needs_supplier_order": 0,
    }


def test_confirmed_unallocated_needs_supplier_order(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Unalloc")
    preorder = _preorder(db_session, customer.id, product.id)
    queue = list_attention(db_session)
    assert _types(queue) == ["preorder_needs_supplier_order"]
    item = queue.items[0]
    assert item.entity_type == "preorder"
    assert item.entity_id == preorder.id
    assert item.supplier_id == supplier.id
    assert item.customer_id == customer.id
    assert item.product_id == product.id
    assert queue.counts.preorder_needs_supplier_order == 1


def test_allocated_confirmed_excluded_and_draft_needs_placement(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Draft")
    preorder = _preorder(db_session, customer.id, product.id)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    queue = list_attention(db_session)
    assert _types(queue) == ["supplier_order_draft_needs_placement"]
    assert queue.items[0].entity_id == draft.id
    assert queue.counts.preorder_needs_supplier_order == 0
    assert queue.counts.supplier_order_draft_needs_placement == 1


def test_placed_confirmed_dispatched_supplier_orders_excluded(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="InFlight")
    preorder = _preorder(db_session, customer.id, product.id)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    place_supplier_order(db_session, draft.id)
    assert _types(list_attention(db_session)) == []
    transition_supplier_order(
        db_session, draft.id, SupplierOrderTransition(status="CONFIRMED")
    )
    assert _types(list_attention(db_session)) == []
    transition_supplier_order(
        db_session, draft.id, SupplierOrderTransition(status="DISPATCHED")
    )
    assert _types(list_attention(db_session)) == []


def test_arrived_supplier_order_needs_reconciliation(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="ArriveSO")
    preorder = _preorder(db_session, customer.id, product.id, quantity=1)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    _arrive_order(db_session, draft.id)
    queue = list_attention(db_session)
    assert "supplier_order_needs_reconciliation" in _types(queue)
    assert queue.counts.supplier_order_needs_reconciliation == 1
    assert queue.counts.preorder_needs_supplier_order == 0


def test_reconcile_then_ready_then_fulfil_disappears(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Flow")
    preorder = _preorder(db_session, customer.id, product.id, quantity=1)
    draft = generate_supplier_order_draft(db_session, supplier.id, [preorder.id])
    _arrive_order(db_session, draft.id)
    loaded = reconcile_supplier_order(
        db_session,
        draft.id,
        SupplierOrderReconcile(
            lines=[
                ReconciliationLineInput(
                    line_id=draft.lines[0].id, received_quantity=1
                )
            ]
        ),
    )
    assert loaded.status == "RECONCILED"
    queue = list_attention(db_session)
    assert _types(queue) == ["preorder_needs_customer_ready"]
    assert queue.items[0].entity_id == preorder.id
    transition_preorder(
        db_session, preorder.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )
    queue = list_attention(db_session)
    assert _types(queue) == ["preorder_needs_fulfilment"]
    transition_preorder(db_session, preorder.id, PreorderTransition(status="FULFILLED"))
    assert _types(list_attention(db_session)) == []


def test_terminal_preorders_and_open_enquiry_excluded(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Terminal")
    cancelled = _preorder(db_session, customer.id, product.id)
    transition_preorder(db_session, cancelled.id, PreorderTransition(status="CANCELLED"))
    unavailable = _preorder(db_session, customer.id, product.id)
    transition_preorder(
        db_session, unavailable.id, PreorderTransition(status="SUPPLIER_UNAVAILABLE")
    )
    create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer.id, product_id=product.id),
    )
    assert _types(list_attention(db_session)) == []


def test_unpaid_and_partial_do_not_create_payment_attention(
    db_session: Session,
) -> None:
    _supplier, product, customer = _catalogue(db_session, suffix="PayNoise")
    unpaid = _preorder(
        db_session, customer.id, product.id, agreed_price=Decimal("85.00")
    )
    partial = _preorder(
        db_session, customer.id, product.id, agreed_price=Decimal("85.00")
    )
    create_payment(
        db_session,
        partial.id,
        PaymentCreate(amount=Decimal("40.00"), method="REVOLUT"),
    )
    queue = list_attention(db_session)
    assert set(_types(queue)) == {"preorder_needs_supplier_order"}
    assert {item.entity_id for item in queue.items} == {unpaid.id, partial.id}
    assert queue.counts.preorder_overpaid == 0


def test_overpaid_bulk_and_same_preorder_can_have_two_types(
    db_session: Session,
) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Over")
    first = _preorder(
        db_session, customer.id, product.id, quantity=1, agreed_price=Decimal("50.00")
    )
    second = _preorder(
        db_session, customer.id, product.id, quantity=1, agreed_price=Decimal("50.00")
    )
    create_payment(
        db_session, first.id, PaymentCreate(amount=Decimal("60.00"), method="REVOLUT")
    )
    create_payment(
        db_session,
        second.id,
        PaymentCreate(amount=Decimal("80.00"), method="BANK_TRANSFER"),
    )
    draft = generate_supplier_order_draft(db_session, supplier.id, [first.id])
    _arrive_order(db_session, draft.id)
    reconcile_supplier_order(
        db_session,
        draft.id,
        SupplierOrderReconcile(
            lines=[
                ReconciliationLineInput(
                    line_id=draft.lines[0].id, received_quantity=1
                )
            ]
        ),
    )
    transition_preorder(
        db_session, first.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )
    queue = list_attention(db_session)
    types_by_id: dict[int, set[str]] = {}
    for item in queue.items:
        types_by_id.setdefault(item.entity_id, set()).add(item.type)
    assert types_by_id[first.id] == {
        "preorder_overpaid",
        "preorder_needs_fulfilment",
    }
    assert types_by_id[second.id] == {
        "preorder_overpaid",
        "preorder_needs_supplier_order",
    }
    overpaid = [item for item in queue.items if item.type == "preorder_overpaid"]
    assert len(overpaid) == 2
    assert {item.entity_id for item in overpaid} == {first.id, second.id}
    assert all(item.outstanding_balance < 0 for item in overpaid)
    keys = [(item.type, item.entity_type, item.entity_id) for item in queue.items]
    assert len(keys) == len(set(keys))
    assert queue.counts.preorder_overpaid == 2


def test_deterministic_category_order(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="Order")
    unallocated = _preorder(db_session, customer.id, product.id)
    draft_preorder = _preorder(db_session, customer.id, product.id)
    over = _preorder(
        db_session, customer.id, product.id, agreed_price=Decimal("10.00")
    )
    create_payment(
        db_session, over.id, PaymentCreate(amount=Decimal("20.00"), method="REVOLUT")
    )
    draft = generate_supplier_order_draft(db_session, supplier.id, [draft_preorder.id])
    queue = list_attention(db_session)
    assert _types(queue) == [
        "preorder_overpaid",
        "supplier_order_draft_needs_placement",
        "preorder_needs_supplier_order",
        "preorder_needs_supplier_order",
    ]
    assert queue.items[0].entity_id == over.id
    assert queue.items[1].entity_id == draft.id
    confirmed_ids = [
        item.entity_id
        for item in queue.items
        if item.type == "preorder_needs_supplier_order"
    ]
    assert confirmed_ids == sorted(confirmed_ids)
    assert unallocated.id in confirmed_ids
    assert over.id in confirmed_ids
