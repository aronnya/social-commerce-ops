import pytest
from pydantic import ValidationError

from app.schemas import ReconciliationLineInput, SupplierOrderReconcile


def test_valid_reconciliation_payload() -> None:
    payload = SupplierOrderReconcile(
        lines=[
            ReconciliationLineInput(
                line_id=1,
                received_quantity=2,
                arrived_preorder_ids=[10],
            )
        ],
        reconciliation_notes="short one unit",
    )
    assert payload.lines[0].line_id == 1
    assert payload.lines[0].received_quantity == 2
    assert payload.lines[0].arrived_preorder_ids == [10]
    assert payload.reconciliation_notes == "short one unit"


def test_received_quantity_zero_accepted() -> None:
    line = ReconciliationLineInput(line_id=1, received_quantity=0)
    assert line.received_quantity == 0


def test_negative_received_quantity_rejected() -> None:
    with pytest.raises(ValidationError):
        ReconciliationLineInput(line_id=1, received_quantity=-1)


def test_duplicate_line_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderReconcile(
            lines=[
                ReconciliationLineInput(line_id=1, received_quantity=1),
                ReconciliationLineInput(line_id=1, received_quantity=2),
            ]
        )


def test_duplicate_arrived_preorder_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        ReconciliationLineInput(
            line_id=1,
            received_quantity=2,
            arrived_preorder_ids=[10, 10],
        )


def test_empty_lines_rejected() -> None:
    with pytest.raises(ValidationError):
        SupplierOrderReconcile(lines=[])


def test_blank_reconciliation_notes_become_null() -> None:
    payload = SupplierOrderReconcile(
        lines=[ReconciliationLineInput(line_id=1, received_quantity=0)],
        reconciliation_notes="   ",
    )
    assert payload.reconciliation_notes is None


def test_non_blank_reconciliation_notes_are_trimmed() -> None:
    payload = SupplierOrderReconcile(
        lines=[ReconciliationLineInput(line_id=1, received_quantity=0)],
        reconciliation_notes="  short one unit  ",
    )
    assert payload.reconciliation_notes == "short one unit"


def test_empty_arrived_preorder_ids_accepted() -> None:
    line = ReconciliationLineInput(
        line_id=1,
        received_quantity=2,
        arrived_preorder_ids=[],
    )
    assert line.arrived_preorder_ids == []


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ReconciliationLineInput(line_id=1, received_quantity=1, notes="no")
    with pytest.raises(ValidationError):
        SupplierOrderReconcile(
            lines=[ReconciliationLineInput(line_id=1, received_quantity=1)],
            status="RECONCILED",
        )
