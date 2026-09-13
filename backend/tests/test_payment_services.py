from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas import (
    CustomerCreate,
    PaymentCreate,
    PaymentUpdate,
    PreorderCreate,
    PreorderUpdate,
    ProductCreate,
    SupplierCreate,
)
from app.services import (
    ConflictError,
    NotFoundError,
    create_customer,
    create_payment,
    create_preorder,
    create_product,
    create_supplier,
    get_payment,
    get_preorder,
    list_payments,
    payment_summary,
    update_payment,
    update_preorder,
)


def _priced_preorder(
    db: Session,
    *,
    selling_price: Decimal | None = Decimal("85.00"),
    agreed_price: Decimal | None | object = ...,
    quantity: int = 1,
):
    supplier = create_supplier(db, SupplierCreate(name="Demo Payment Supplier"))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name="Demo Payment Dress",
            selling_price=selling_price,
        ),
    )
    customer = create_customer(db, CustomerCreate(name="Demo Payment Customer"))
    payload: dict = {"customer_id": customer.id, "product_id": product.id, "quantity": quantity}
    if agreed_price is not ...:
        payload["agreed_price"] = agreed_price
    return create_preorder(db, PreorderCreate(**payload))


def test_create_payment_on_priced_preorder(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    payment = create_payment(
        db_session,
        preorder.id,
        PaymentCreate(amount=Decimal("40.00"), method="REVOLUT"),
    )
    assert payment.preorder_id == preorder.id
    assert payment.amount == Decimal("40.00")
    assert payment.paid_at is not None
    assert get_preorder(db_session, preorder.id).status == "CONFIRMED"


def test_create_payment_missing_preorder(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        create_payment(
            db_session,
            999999,
            PaymentCreate(amount=Decimal("10.00"), method="BANK_TRANSFER"),
        )


def test_create_payment_null_agreed_price_conflicts(db_session: Session) -> None:
    preorder = _priced_preorder(db_session, selling_price=None, agreed_price=None)
    with pytest.raises(ConflictError):
        create_payment(
            db_session,
            preorder.id,
            PaymentCreate(amount=Decimal("10.00"), method="REVOLUT"),
        )


def test_multiple_payments_allowed(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("40.00"), method="REVOLUT")
    )
    create_payment(
        db_session,
        preorder.id,
        PaymentCreate(amount=Decimal("45.00"), method="BANK_TRANSFER"),
    )
    listed = list_payments(db_session, preorder.id)
    assert len(listed) == 2
    assert get_preorder(db_session, preorder.id).status == "CONFIRMED"


def test_list_payments_missing_preorder(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        list_payments(db_session, 999999)


def test_list_and_get_payments(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    other = _priced_preorder(db_session)
    payment = create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("10.00"), method="REVOLUT")
    )
    create_payment(
        db_session, other.id, PaymentCreate(amount=Decimal("5.00"), method="REVOLUT")
    )
    listed = list_payments(db_session, preorder.id)
    assert [item.id for item in listed] == [payment.id]
    fetched = get_payment(db_session, preorder.id, payment.id)
    assert fetched.id == payment.id
    with pytest.raises(NotFoundError):
        get_payment(db_session, other.id, payment.id)
    with pytest.raises(NotFoundError):
        get_payment(db_session, preorder.id, 999999)


def test_update_payment_reference_and_notes(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    payment = create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("10.00"), method="REVOLUT")
    )
    updated = update_payment(
        db_session,
        preorder.id,
        payment.id,
        PaymentUpdate(reference="REV-1", notes="first instalment"),
    )
    assert updated.reference == "REV-1"
    assert updated.notes == "first instalment"
    assert updated.amount == Decimal("10.00")
    assert updated.method == "REVOLUT"


def test_payment_update_cannot_change_amount_or_method() -> None:
    with pytest.raises(ValidationError):
        PaymentUpdate(amount=Decimal("99.00"))
    with pytest.raises(ValidationError):
        PaymentUpdate(method="BANK_TRANSFER")


def test_payment_summary_exact_single_payment(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("85.00"), method="REVOLUT")
    )
    summary = payment_summary(db_session, get_preorder(db_session, preorder.id))
    assert summary.status == "PAID"
    assert summary.amount_paid == Decimal("85.00")
    assert summary.outstanding_balance == Decimal("0.00")


def test_payment_summary_unpaid_partial_paid_overpaid(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    unpaid = payment_summary(db_session, preorder)
    assert unpaid.status == "UNPAID"
    assert unpaid.total_amount == Decimal("85.00")
    assert unpaid.amount_paid == Decimal("0")
    assert unpaid.outstanding_balance == Decimal("85.00")

    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("40.00"), method="REVOLUT")
    )
    partial = payment_summary(db_session, get_preorder(db_session, preorder.id))
    assert partial.status == "PARTIALLY_PAID"
    assert partial.amount_paid == Decimal("40.00")
    assert partial.outstanding_balance == Decimal("45.00")

    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("45.00"), method="REVOLUT")
    )
    paid = payment_summary(db_session, get_preorder(db_session, preorder.id))
    assert paid.status == "PAID"
    assert paid.outstanding_balance == Decimal("0")

    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("1.00"), method="REVOLUT")
    )
    overpaid = payment_summary(db_session, get_preorder(db_session, preorder.id))
    assert overpaid.status == "OVERPAID"
    assert overpaid.outstanding_balance == Decimal("-1.00")


def test_payment_summary_null_agreed_price(db_session: Session) -> None:
    preorder = _priced_preorder(db_session, selling_price=None, agreed_price=None)
    summary = payment_summary(db_session, preorder)
    assert summary.total_amount is None
    assert summary.outstanding_balance is None
    assert summary.status is None
    assert summary.amount_paid == Decimal("0")


def test_payment_summary_zero_total(db_session: Session) -> None:
    preorder = _priced_preorder(db_session, agreed_price=Decimal("0.00"))
    unpaid_zero = payment_summary(db_session, preorder)
    assert unpaid_zero.total_amount == Decimal("0.00")
    assert unpaid_zero.status == "PAID"
    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("1.00"), method="REVOLUT")
    )
    over = payment_summary(db_session, get_preorder(db_session, preorder.id))
    assert over.status == "OVERPAID"


def test_preorder_freeze_after_payment(db_session: Session) -> None:
    preorder = _priced_preorder(db_session)
    update_preorder(db_session, preorder.id, PreorderUpdate(quantity=2))
    update_preorder(
        db_session, preorder.id, PreorderUpdate(agreed_price=Decimal("80.00"))
    )
    create_payment(
        db_session, preorder.id, PaymentCreate(amount=Decimal("10.00"), method="REVOLUT")
    )
    with pytest.raises(ConflictError):
        update_preorder(db_session, preorder.id, PreorderUpdate(quantity=3))
    with pytest.raises(ConflictError):
        update_preorder(
            db_session, preorder.id, PreorderUpdate(agreed_price=Decimal("70.00"))
        )
    notes = update_preorder(db_session, preorder.id, PreorderUpdate(notes="paid deposit"))
    assert notes.notes == "paid deposit"
    assert notes.status == "CONFIRMED"
