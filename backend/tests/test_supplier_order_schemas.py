from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import (
    SupplierOrderGenerateDraft,
    SupplierOrderRead,
    SupplierOrderTransition,
    SupplierOrderUpdate,
)


def test_supplier_order_update_accepts_notes() -> None:
    updated = SupplierOrderUpdate(notes="review quantities")
    assert updated.notes == "review quantities"


def test_supplier_order_update_trims_notes() -> None:
    updated = SupplierOrderUpdate(notes="  review quantities  ")
    assert updated.notes == "review quantities"


def test_supplier_order_update_whitespace_only_notes_become_null() -> None:
    updated = SupplierOrderUpdate(notes="   ")
    assert updated.notes is None


def test_supplier_order_update_rejects_status() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderUpdate(status="DRAFT")


def test_supplier_order_update_rejects_supplier_id() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderUpdate(supplier_id=1)


def test_supplier_order_update_rejects_lines() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderUpdate(lines=[])


def test_generate_draft_requires_supplier_id() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderGenerateDraft()


def test_generate_draft_accepts_supplier_id() -> None:
    payload = SupplierOrderGenerateDraft(supplier_id=1)
    assert payload.supplier_id == 1
    assert payload.preorder_ids is None


def test_generate_draft_omitted_preorder_ids_accepted() -> None:
    payload = SupplierOrderGenerateDraft(supplier_id=1)
    assert payload.preorder_ids is None


def test_generate_draft_accepts_preorder_ids() -> None:
    payload = SupplierOrderGenerateDraft(supplier_id=1, preorder_ids=[10, 11])
    assert payload.preorder_ids == [10, 11]


def test_generate_draft_rejects_empty_preorder_ids() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderGenerateDraft(supplier_id=1, preorder_ids=[])


def test_generate_draft_rejects_duplicate_preorder_ids() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderGenerateDraft(supplier_id=1, preorder_ids=[10, 10])


def test_generate_draft_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderGenerateDraft(supplier_id=1, status="DRAFT")


def test_supplier_order_transition_accepts_allowed_targets() -> None:
    assert SupplierOrderTransition(status="CONFIRMED").status == "CONFIRMED"
    assert SupplierOrderTransition(status="DISPATCHED").status == "DISPATCHED"
    assert SupplierOrderTransition(status="ARRIVED").status == "ARRIVED"


def test_supplier_order_transition_rejects_reconciled() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderTransition(status="RECONCILED")


def test_supplier_order_transition_rejects_draft() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderTransition(status="DRAFT")


def test_supplier_order_transition_rejects_placed() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderTransition(status="PLACED")


def test_supplier_order_transition_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderTransition(status="CANCELLED")


def test_supplier_order_transition_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderTransition(status="CONFIRMED", notes="no")


def test_supplier_order_read_nested_shape() -> None:
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    read = SupplierOrderRead(
        id=1,
        supplier_id=2,
        status="DRAFT",
        notes=None,
        placed_at=None,
        created_at=now,
        updated_at=now,
        lines=[
            {
                "id": 1,
                "product_id": 9,
                "quantity": 3,
                "unit_cost": Decimal("10.00"),
                "notes": None,
                "allocations": [
                    {"id": 1, "preorder_id": 4, "quantity": 2},
                    {"id": 2, "preorder_id": 5, "quantity": 1},
                ],
            }
        ],
    )
    assert read.status == "DRAFT"
    assert read.lines[0].quantity == 3
    assert read.lines[0].received_quantity is None
    assert read.reconciled_at is None
    assert read.reconciliation_notes is None
    assert len(read.lines[0].allocations) == 2


def test_supplier_order_read_rejects_zero_quantities_and_negative_cost() -> None:
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    base = {
        "id": 1,
        "supplier_id": 2,
        "status": "DRAFT",
        "notes": None,
        "placed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    with pytest.raises(ValidationError):
        SupplierOrderRead(
            **base,
            lines=[
                {
                    "id": 1,
                    "product_id": 9,
                    "quantity": 0,
                    "unit_cost": None,
                    "notes": None,
                    "allocations": [{"id": 1, "preorder_id": 4, "quantity": 1}],
                }
            ],
        )
    with pytest.raises(ValidationError):
        SupplierOrderRead(
            **base,
            lines=[
                {
                    "id": 1,
                    "product_id": 9,
                    "quantity": 1,
                    "unit_cost": None,
                    "notes": None,
                    "allocations": [{"id": 1, "preorder_id": 4, "quantity": 0}],
                }
            ],
        )
    with pytest.raises(ValidationError):
        SupplierOrderRead(
            **base,
            lines=[
                {
                    "id": 1,
                    "product_id": 9,
                    "quantity": 1,
                    "unit_cost": Decimal("-0.01"),
                    "notes": None,
                    "allocations": [{"id": 1, "preorder_id": 4, "quantity": 1}],
                }
            ],
        )
