from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import EnquiryCreate, EnquiryUpdate


def test_enquiry_create_rejects_quantity_zero() -> None:
    with pytest.raises(ValidationError):
        EnquiryCreate(customer_id=1, product_id=1, quantity=0)
    with pytest.raises(ValidationError):
        EnquiryUpdate(quantity=0)


def test_enquiry_create_rejects_negative_quantity() -> None:
    with pytest.raises(ValidationError):
        EnquiryCreate(customer_id=1, product_id=1, quantity=-1)
    with pytest.raises(ValidationError):
        EnquiryUpdate(quantity=-1)


def test_enquiry_rejects_invalid_outcome() -> None:
    with pytest.raises(ValidationError):
        EnquiryCreate(customer_id=1, product_id=1, outcome="LOST")
    with pytest.raises(ValidationError):
        EnquiryUpdate(outcome="preordered")


def test_enquiry_accepts_valid_outcome() -> None:
    created = EnquiryCreate(customer_id=1, product_id=1, outcome="TOO_EXPENSIVE")
    assert created.outcome == "TOO_EXPENSIVE"

    updated = EnquiryUpdate(outcome="NOT_INTERESTED")
    assert updated.outcome == "NOT_INTERESTED"

    cleared = EnquiryUpdate(outcome=None)
    assert cleared.outcome is None


def test_enquiry_notes_are_trimmed() -> None:
    created = EnquiryCreate(customer_id=1, product_id=1, notes="  asked in Messenger  ")
    assert created.notes == "asked in Messenger"

    updated = EnquiryUpdate(notes="  follow up  ")
    assert updated.notes == "follow up"


def test_enquiry_whitespace_only_notes_become_null() -> None:
    created = EnquiryCreate(customer_id=1, product_id=1, notes="   ")
    assert created.notes is None

    updated = EnquiryUpdate(notes="   ")
    assert updated.notes is None


def test_enquiry_update_rejects_customer_and_product_id() -> None:
    assert "customer_id" not in EnquiryUpdate.model_fields
    assert "product_id" not in EnquiryUpdate.model_fields
    with pytest.raises(ValidationError):
        EnquiryUpdate(customer_id=9)
    with pytest.raises(ValidationError):
        EnquiryUpdate(product_id=9)


def test_enquiry_accepts_timezone_aware_enquired_at() -> None:
    when = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    created = EnquiryCreate(customer_id=1, product_id=1, enquired_at=when)
    assert created.enquired_at == when

    updated = EnquiryUpdate(enquired_at=when)
    assert updated.enquired_at == when
