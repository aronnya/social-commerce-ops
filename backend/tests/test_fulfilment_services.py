from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Fulfilment
from app.schemas import (
    CustomerCreate,
    FulfilmentCreate,
    FulfilmentRead,
    PaymentCreate,
    PreorderCreate,
    PreorderRead,
    PreorderTransition,
    ProductCreate,
    ReconciliationLineInput,
    SupplierCreate,
    SupplierOrderReconcile,
    SupplierOrderTransition,
)
from app.services import (
    PREORDER_ALLOWED_TRANSITIONS,
    ConflictError,
    NotFoundError,
    create_customer,
    create_payment,
    create_preorder,
    create_product,
    create_supplier,
    fulfil_preorder,
    generate_supplier_order_draft,
    get_preorder,
    list_attention,
    payment_summary,
    place_supplier_order,
    reconcile_supplier_order,
    transition_preorder,
    transition_supplier_order,
)


POST_ADDRESS = "Test Recipient\n1 Test Street\nTest Town"


def _catalogue(db: Session, *, suffix: str):
    supplier = create_supplier(db, SupplierCreate(name=f"Demo Fulfil {suffix} Supplier"))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name=f"Demo Fulfil {suffix} Dress",
            supplier_cost=Decimal("40.00"),
            selling_price=Decimal("85.00"),
        ),
    )
    customer = create_customer(db, CustomerCreate(name=f"Demo Fulfil {suffix} Customer"))
    return supplier, product, customer


def _ready_preorder(db: Session, *, suffix: str, quantity: int = 1):
    supplier, product, customer = _catalogue(db, suffix=suffix)
    preorder = create_preorder(
        db,
        PreorderCreate(
            customer_id=customer.id,
            product_id=product.id,
            quantity=quantity,
        ),
    )
    draft = generate_supplier_order_draft(db, supplier.id, [preorder.id])
    place_supplier_order(db, draft.id)
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        transition_supplier_order(db, draft.id, SupplierOrderTransition(status=status))
    reconcile_supplier_order(
        db,
        draft.id,
        SupplierOrderReconcile(
            lines=[
                ReconciliationLineInput(
                    line_id=draft.lines[0].id, received_quantity=quantity
                )
            ]
        ),
    )
    return transition_preorder(
        db, preorder.id, PreorderTransition(status="READY_FOR_CUSTOMER")
    )


def test_generic_ready_for_customer_allows_only_cancelled() -> None:
    assert PREORDER_ALLOWED_TRANSITIONS["READY_FOR_CUSTOMER"] == frozenset({"CANCELLED"})


def test_home_collection_happy_path(db_session: Session) -> None:
    preorder = _ready_preorder(db_session, suffix="Home")
    fulfilled = fulfil_preorder(
        db_session, preorder.id, FulfilmentCreate(method="HOME_COLLECTION")
    )
    assert fulfilled.status == "FULFILLED"
    assert fulfilled.fulfilment is not None
    assert fulfilled.fulfilment.method == "HOME_COLLECTION"
    assert fulfilled.fulfilment.postage_type is None
    assert fulfilled.fulfilment.delivery_address is None
    assert fulfilled.fulfilment.postage_cost is None
    assert fulfilled.fulfilment.tracking_reference is None
    assert fulfilled.fulfilment.fulfilled_at.tzinfo is not None
    count = db_session.scalar(
        select(func.count()).select_from(Fulfilment).where(
            Fulfilment.preorder_id == preorder.id
        )
    )
    assert count == 1


def test_post_regular_with_and_without_postage_cost(db_session: Session) -> None:
    with_cost = _ready_preorder(db_session, suffix="RegCost")
    fulfilled = fulfil_preorder(
        db_session,
        with_cost.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("4.50"),
        ),
    )
    assert fulfilled.fulfilment.postage_cost == Decimal("4.50")
    assert fulfilled.fulfilment.tracking_reference is None

    without_cost = _ready_preorder(db_session, suffix="RegNone")
    fulfilled_none = fulfil_preorder(
        db_session,
        without_cost.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
        ),
    )
    assert fulfilled_none.fulfilment.postage_cost is None


def test_post_registered_with_and_without_postage_cost(db_session: Session) -> None:
    with_cost = _ready_preorder(db_session, suffix="RegdCost")
    fulfilled = fulfil_preorder(
        db_session,
        with_cost.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGISTERED",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("9.20"),
            tracking_reference="TEST-REG-12345",
        ),
    )
    assert fulfilled.fulfilment.postage_cost == Decimal("9.20")
    assert fulfilled.fulfilment.tracking_reference == "TEST-REG-12345"

    without_cost = _ready_preorder(db_session, suffix="RegdNone")
    fulfilled_none = fulfil_preorder(
        db_session,
        without_cost.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGISTERED",
            delivery_address=POST_ADDRESS,
            tracking_reference="TEST-REG-67890",
        ),
    )
    assert fulfilled_none.fulfilment.postage_cost is None


def test_zero_postage_cost_allowed_for_post(db_session: Session) -> None:
    preorder = _ready_preorder(db_session, suffix="ZeroCost")
    fulfilled = fulfil_preorder(
        db_session,
        preorder.id,
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("0"),
        ),
    )
    assert fulfilled.fulfilment.postage_cost == Decimal("0")


def test_schema_rejects_invalid_fulfilment_payloads() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="POST", postage_type="REGULAR")
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="POST", delivery_address=POST_ADDRESS)
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="HOME_COLLECTION", postage_type="REGULAR", delivery_address=POST_ADDRESS
        )
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            tracking_reference="TEST-REG-12345",
        )
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGISTERED",
            delivery_address=POST_ADDRESS,
        )
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("-1.00"),
        )


def test_wrong_state_cancelled_and_unavailable_rejected(db_session: Session) -> None:
    supplier, product, customer = _catalogue(db_session, suffix="States")
    confirmed = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer.id, product_id=product.id),
    )
    payload = FulfilmentCreate(method="HOME_COLLECTION")
    with pytest.raises(ConflictError):
        fulfil_preorder(db_session, confirmed.id, payload)
    cancelled = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer.id, product_id=product.id),
    )
    transition_preorder(db_session, cancelled.id, PreorderTransition(status="CANCELLED"))
    with pytest.raises(ConflictError):
        fulfil_preorder(db_session, cancelled.id, payload)
    unavailable = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer.id, product_id=product.id),
    )
    transition_preorder(
        db_session, unavailable.id, PreorderTransition(status="SUPPLIER_UNAVAILABLE")
    )
    with pytest.raises(ConflictError):
        fulfil_preorder(db_session, unavailable.id, payload)
    with pytest.raises(NotFoundError):
        fulfil_preorder(db_session, 999999, payload)


def test_duplicate_fulfilment_rejected(db_session: Session) -> None:
    preorder = _ready_preorder(db_session, suffix="Dup")
    fulfil_preorder(db_session, preorder.id, FulfilmentCreate(method="HOME_COLLECTION"))
    with pytest.raises(ConflictError):
        fulfil_preorder(db_session, preorder.id, FulfilmentCreate(method="HOME_COLLECTION"))
    count = db_session.scalar(
        select(func.count()).select_from(Fulfilment).where(
            Fulfilment.preorder_id == preorder.id
        )
    )
    assert count == 1
    assert get_preorder(db_session, preorder.id).status == "FULFILLED"


def test_generic_transition_to_fulfilled_rejected(db_session: Session) -> None:
    preorder = _ready_preorder(db_session, suffix="Generic")
    with pytest.raises(ValidationError):
        PreorderTransition(status="FULFILLED")
    with pytest.raises(ConflictError):
        transition_preorder(
            db_session, preorder.id, PreorderTransition(status="ORDERED_FROM_SUPPLIER")
        )
    assert get_preorder(db_session, preorder.id).status == "READY_FOR_CUSTOMER"
    cancelled = transition_preorder(
        db_session, preorder.id, PreorderTransition(status="CANCELLED")
    )
    assert cancelled.status == "CANCELLED"
    count = db_session.scalar(
        select(func.count()).select_from(Fulfilment).where(
            Fulfilment.preorder_id == preorder.id
        )
    )
    assert count == 0


def test_atomic_create_and_commit_failure_rolls_back(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    preorder = _ready_preorder(db_session, suffix="Atomic")
    fulfilled = fulfil_preorder(
        db_session, preorder.id, FulfilmentCreate(method="HOME_COLLECTION")
    )
    assert fulfilled.status == "FULFILLED"
    assert fulfilled.fulfilment.preorder_id == preorder.id

    other = _ready_preorder(db_session, suffix="Rollback")
    real_flush = db_session.flush

    def flush_then_fail(*args, **kwargs):
        real_flush(*args, **kwargs)
        raise IntegrityError(
            "INSERT INTO fulfilments",
            {},
            Exception("uq_fulfilments_preorder_id"),
        )

    monkeypatch.setattr(db_session, "flush", flush_then_fail)
    with pytest.raises(ConflictError):
        fulfil_preorder(db_session, other.id, FulfilmentCreate(method="HOME_COLLECTION"))
    db_session.expire_all()
    reloaded = get_preorder(db_session, other.id)
    assert reloaded.status == "READY_FOR_CUSTOMER"
    count = db_session.scalar(
        select(func.count()).select_from(Fulfilment).where(
            Fulfilment.preorder_id == other.id
        )
    )
    assert count == 0


def test_payment_state_does_not_gate_and_totals_unchanged(db_session: Session) -> None:
    unpaid = _ready_preorder(db_session, suffix="Unpaid")
    assert payment_summary(db_session, unpaid).status == "UNPAID"
    fulfil_preorder(db_session, unpaid.id, FulfilmentCreate(method="HOME_COLLECTION"))

    partial = _ready_preorder(db_session, suffix="Partial")
    create_payment(
        db_session,
        partial.id,
        PaymentCreate(amount=Decimal("20.00"), method="REVOLUT"),
    )
    before = payment_summary(db_session, partial)
    assert before.status == "PARTIALLY_PAID"
    fulfil_preorder(db_session, partial.id, FulfilmentCreate(method="HOME_COLLECTION"))
    after = payment_summary(db_session, get_preorder(db_session, partial.id))
    assert after.status == "PARTIALLY_PAID"
    assert after.amount_paid == Decimal("20.00")
    assert after.total_amount == before.total_amount

    paid = _ready_preorder(db_session, suffix="Paid")
    create_payment(
        db_session, paid.id, PaymentCreate(amount=Decimal("85.00"), method="REVOLUT")
    )
    fulfil_preorder(db_session, paid.id, FulfilmentCreate(method="HOME_COLLECTION"))
    assert payment_summary(db_session, get_preorder(db_session, paid.id)).status == "PAID"

    over = _ready_preorder(db_session, suffix="Over")
    create_payment(
        db_session, over.id, PaymentCreate(amount=Decimal("90.00"), method="REVOLUT")
    )
    fulfil_preorder(db_session, over.id, FulfilmentCreate(method="HOME_COLLECTION"))
    summary = payment_summary(db_session, get_preorder(db_session, over.id))
    assert summary.status == "OVERPAID"
    assert summary.amount_paid == Decimal("90.00")


def test_attention_item_disappears_after_fulfilment(db_session: Session) -> None:
    preorder = _ready_preorder(db_session, suffix="Attention")
    types = [item.type for item in list_attention(db_session).items]
    assert types == ["preorder_needs_fulfilment"]
    fulfil_preorder(db_session, preorder.id, FulfilmentCreate(method="HOME_COLLECTION"))
    assert [item.type for item in list_attention(db_session).items] == []


def test_preorder_read_exposes_fulfilment(db_session: Session) -> None:
    preorder = _ready_preorder(db_session, suffix="Read")
    summary = payment_summary(db_session, preorder)
    before = PreorderRead.model_validate(
        {
            **{
                name: getattr(preorder, name)
                for name in PreorderRead.model_fields
                if name not in {"payment_summary", "fulfilment"}
            },
            "payment_summary": summary,
            "fulfilment": preorder.fulfilment,
        }
    )
    assert before.fulfilment is None
    fulfilled = fulfil_preorder(
        db_session, preorder.id, FulfilmentCreate(method="HOME_COLLECTION")
    )
    after = PreorderRead.model_validate(
        {
            **{
                name: getattr(fulfilled, name)
                for name in PreorderRead.model_fields
                if name not in {"payment_summary", "fulfilment"}
            },
            "payment_summary": payment_summary(db_session, fulfilled),
            "fulfilment": fulfilled.fulfilment,
        }
    )
    assert after.status == "FULFILLED"
    assert FulfilmentRead.model_validate(after.fulfilment).method == "HOME_COLLECTION"
