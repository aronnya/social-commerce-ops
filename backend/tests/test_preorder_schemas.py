from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import PreorderCreate, PreorderTransition, PreorderUpdate


def test_preorder_create_rejects_quantity_zero() -> None:
    with pytest.raises(ValidationError):
        PreorderCreate(customer_id=1, product_id=1, quantity=0)


def test_preorder_create_rejects_negative_quantity() -> None:
    with pytest.raises(ValidationError):
        PreorderCreate(customer_id=1, product_id=1, quantity=-1)


def test_preorder_create_rejects_negative_agreed_price() -> None:
    with pytest.raises(ValidationError):
        PreorderCreate(customer_id=1, product_id=1, agreed_price=Decimal("-1.00"))


def test_preorder_create_notes_are_trimmed() -> None:
    created = PreorderCreate(customer_id=1, product_id=1, notes="  Messenger yes  ")
    assert created.notes == "Messenger yes"


def test_preorder_create_whitespace_only_notes_become_null() -> None:
    created = PreorderCreate(customer_id=1, product_id=1, notes="   ")
    assert created.notes is None


def test_preorder_create_rejects_status() -> None:
    with pytest.raises(ValidationError):
        PreorderCreate(customer_id=1, product_id=1, status="CONFIRMED")


def test_preorder_update_rejects_customer_id() -> None:
    with pytest.raises(ValidationError):
        PreorderUpdate(customer_id=1)


def test_preorder_update_rejects_product_id() -> None:
    with pytest.raises(ValidationError):
        PreorderUpdate(product_id=1)


def test_preorder_update_rejects_enquiry_id() -> None:
    with pytest.raises(ValidationError):
        PreorderUpdate(enquiry_id=1)


def test_preorder_update_rejects_status() -> None:
    with pytest.raises(ValidationError):
        PreorderUpdate(status="ARRIVED")


def test_preorder_update_rejects_quantity_zero() -> None:
    with pytest.raises(ValidationError):
        PreorderUpdate(quantity=0)


def test_preorder_update_rejects_negative_agreed_price() -> None:
    with pytest.raises(ValidationError):
        PreorderUpdate(agreed_price=Decimal("-0.01"))


def test_preorder_transition_accepts_valid_status() -> None:
    transition = PreorderTransition(status="ARRIVED")
    assert transition.status == "ARRIVED"


def test_preorder_transition_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        PreorderTransition(status="INQUIRY")
    with pytest.raises(ValidationError):
        PreorderTransition(status="PAID")
