from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import (
    FulfilmentCreate,
    FulfilmentRead,
    PaymentSummary,
    PreorderRead,
    PreorderTransition,
)


POST_ADDRESS = "Test Recipient\n1 Test Street\nTest Town"


def test_home_collection_happy_schema() -> None:
    created = FulfilmentCreate(method="HOME_COLLECTION")
    assert created.method == "HOME_COLLECTION"
    assert created.postage_type is None
    assert created.delivery_address is None
    assert created.postage_cost is None
    assert created.tracking_reference is None


def test_post_regular_with_and_without_postage_cost() -> None:
    with_cost = FulfilmentCreate(
        method="POST",
        postage_type="REGULAR",
        delivery_address=POST_ADDRESS,
        postage_cost=Decimal("4.50"),
    )
    assert with_cost.postage_cost == Decimal("4.50")
    without_cost = FulfilmentCreate(
        method="POST",
        postage_type="REGULAR",
        delivery_address=POST_ADDRESS,
    )
    assert without_cost.postage_cost is None


def test_post_registered_requires_tracking() -> None:
    created = FulfilmentCreate(
        method="POST",
        postage_type="REGISTERED",
        delivery_address=POST_ADDRESS,
        tracking_reference="TEST-REG-12345",
        postage_cost=Decimal("0"),
    )
    assert created.tracking_reference == "TEST-REG-12345"
    assert created.postage_cost == Decimal("0")
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGISTERED",
            delivery_address=POST_ADDRESS,
        )
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGISTERED",
            delivery_address=POST_ADDRESS,
            tracking_reference="   ",
        )


def test_post_missing_or_blank_address() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="POST", postage_type="REGULAR")
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address="   ",
        )


def test_post_missing_postage_type() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="POST", delivery_address=POST_ADDRESS)


def test_home_collection_rejects_post_fields() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="HOME_COLLECTION", postage_type="REGULAR")
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="HOME_COLLECTION", delivery_address=POST_ADDRESS)
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="HOME_COLLECTION", postage_cost=Decimal("1.00"))
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="HOME_COLLECTION", tracking_reference="TEST")


def test_regular_rejects_tracking_reference() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            tracking_reference="TEST-REG-12345",
        )


def test_negative_postage_cost_rejected_zero_allowed() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("-0.01"),
        )
    created = FulfilmentCreate(
        method="POST",
        postage_type="REGULAR",
        delivery_address=POST_ADDRESS,
        postage_cost=Decimal("0"),
    )
    assert created.postage_cost == Decimal("0")


def test_optional_strings_are_trimmed() -> None:
    created = FulfilmentCreate(
        method="POST",
        postage_type="REGISTERED",
        delivery_address=f"  {POST_ADDRESS}  ",
        tracking_reference="  TEST-REG-12345  ",
        notes="  posted today  ",
    )
    assert created.delivery_address == POST_ADDRESS
    assert created.tracking_reference == "TEST-REG-12345"
    assert created.notes == "posted today"


def test_fulfilment_create_rejects_extra_and_fulfilled_at() -> None:
    with pytest.raises(ValidationError):
        FulfilmentCreate(method="HOME_COLLECTION", courier="AN_POST")
    with pytest.raises(ValidationError):
        FulfilmentCreate(
            method="HOME_COLLECTION",
            fulfilled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_preorder_transition_rejects_fulfilled() -> None:
    with pytest.raises(ValidationError):
        PreorderTransition(status="FULFILLED")


def test_preorder_read_exposes_fulfilment_null_and_embedded() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    summary = PaymentSummary(
        total_amount=Decimal("85.00"),
        amount_paid=Decimal("0"),
        outstanding_balance=Decimal("85.00"),
        status="UNPAID",
    )
    empty = PreorderRead(
        id=1,
        customer_id=1,
        product_id=1,
        enquiry_id=None,
        quantity=1,
        status="READY_FOR_CUSTOMER",
        agreed_price=Decimal("85.00"),
        notes=None,
        created_at=now,
        updated_at=now,
        payment_summary=summary,
        fulfilment=None,
    )
    assert empty.fulfilment is None
    embedded = PreorderRead(
        id=1,
        customer_id=1,
        product_id=1,
        enquiry_id=None,
        quantity=1,
        status="FULFILLED",
        agreed_price=Decimal("85.00"),
        notes=None,
        created_at=now,
        updated_at=now,
        payment_summary=summary,
        fulfilment=FulfilmentRead(
            id=9,
            preorder_id=1,
            method="HOME_COLLECTION",
            postage_type=None,
            delivery_address=None,
            postage_cost=None,
            tracking_reference=None,
            notes=None,
            fulfilled_at=now,
            created_at=now,
            updated_at=now,
        ),
    )
    assert embedded.fulfilment is not None
    assert embedded.fulfilment.method == "HOME_COLLECTION"
