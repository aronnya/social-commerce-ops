from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import PaymentCreate, PaymentSummary, PaymentUpdate


def test_payment_create_rejects_amount_zero() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(amount=Decimal("0"), method="REVOLUT")


def test_payment_create_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(amount=Decimal("-1.00"), method="BANK_TRANSFER")


def test_payment_create_rejects_invalid_method() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(amount=Decimal("10.00"), method="CASH")


def test_payment_create_accepts_bank_transfer() -> None:
    created = PaymentCreate(amount=Decimal("10.00"), method="BANK_TRANSFER")
    assert created.method == "BANK_TRANSFER"


def test_payment_create_accepts_revolut() -> None:
    created = PaymentCreate(amount=Decimal("10.00"), method="REVOLUT")
    assert created.method == "REVOLUT"


def test_payment_create_reference_is_trimmed() -> None:
    created = PaymentCreate(
        amount=Decimal("10.00"), method="REVOLUT", reference="  ABC-123  "
    )
    assert created.reference == "ABC-123"


def test_payment_create_whitespace_only_reference_becomes_null() -> None:
    created = PaymentCreate(amount=Decimal("10.00"), method="REVOLUT", reference="   ")
    assert created.reference is None


def test_payment_create_notes_are_trimmed() -> None:
    created = PaymentCreate(
        amount=Decimal("10.00"), method="REVOLUT", notes="  deposit  "
    )
    assert created.notes == "deposit"


def test_payment_create_whitespace_only_notes_become_null() -> None:
    created = PaymentCreate(amount=Decimal("10.00"), method="REVOLUT", notes="   ")
    assert created.notes is None


def test_payment_create_rejects_naive_paid_at() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("10.00"),
            method="REVOLUT",
            paid_at=datetime(2026, 1, 15, 12, 0),
        )


def test_payment_create_accepts_timezone_aware_paid_at() -> None:
    when = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    created = PaymentCreate(amount=Decimal("10.00"), method="REVOLUT", paid_at=when)
    assert created.paid_at == when


def test_payment_create_rejects_status() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(amount=Decimal("10.00"), method="REVOLUT", status="PAID")


def test_payment_create_rejects_preorder_id() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(amount=Decimal("10.00"), method="REVOLUT", preorder_id=1)


def test_payment_update_rejects_amount() -> None:
    with pytest.raises(ValidationError):
        PaymentUpdate(amount=Decimal("5.00"))


def test_payment_update_rejects_method() -> None:
    with pytest.raises(ValidationError):
        PaymentUpdate(method="REVOLUT")


def test_payment_update_rejects_paid_at() -> None:
    with pytest.raises(ValidationError):
        PaymentUpdate(paid_at=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))


def test_payment_update_rejects_preorder_id() -> None:
    with pytest.raises(ValidationError):
        PaymentUpdate(preorder_id=1)


def test_payment_update_trims_reference_and_notes() -> None:
    updated = PaymentUpdate(reference="  REF-9  ", notes="  ok  ")
    assert updated.reference == "REF-9"
    assert updated.notes == "ok"
    cleared = PaymentUpdate(reference="   ", notes="   ")
    assert cleared.reference is None
    assert cleared.notes is None


def test_payment_summary_accepts_known_statuses() -> None:
    unpaid = PaymentSummary(
        total_amount=Decimal("85.00"),
        amount_paid=Decimal("0"),
        outstanding_balance=Decimal("85.00"),
        status="UNPAID",
    )
    assert unpaid.status == "UNPAID"
    partial = PaymentSummary(
        total_amount=Decimal("85.00"),
        amount_paid=Decimal("40.00"),
        outstanding_balance=Decimal("45.00"),
        status="PARTIALLY_PAID",
    )
    assert partial.status == "PARTIALLY_PAID"
    paid = PaymentSummary(
        total_amount=Decimal("85.00"),
        amount_paid=Decimal("85.00"),
        outstanding_balance=Decimal("0"),
        status="PAID",
    )
    assert paid.status == "PAID"
    overpaid = PaymentSummary(
        total_amount=Decimal("85.00"),
        amount_paid=Decimal("90.00"),
        outstanding_balance=Decimal("-5.00"),
        status="OVERPAID",
    )
    assert overpaid.status == "OVERPAID"


def test_payment_summary_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        PaymentSummary(
            total_amount=Decimal("85.00"),
            amount_paid=Decimal("0"),
            outstanding_balance=Decimal("85.00"),
            status="PENDING",
        )


def test_payment_summary_allows_null_status_when_total_unknown() -> None:
    summary = PaymentSummary(
        total_amount=None,
        amount_paid=Decimal("0"),
        outstanding_balance=None,
        status=None,
    )
    assert summary.status is None
    assert summary.total_amount is None
