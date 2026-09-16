from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import AttentionCounts, AttentionItem, AttentionQueue


def test_attention_item_accepts_workflow_fields() -> None:
    item = AttentionItem(
        type="preorder_needs_supplier_order",
        entity_type="preorder",
        entity_id=3,
        occurred_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        customer_id=1,
        product_id=2,
        supplier_id=4,
    )
    assert item.type == "preorder_needs_supplier_order"
    assert item.outstanding_balance is None


def test_attention_item_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        AttentionItem(
            type="open_enquiry",
            entity_type="preorder",
            entity_id=1,
            occurred_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        )


def test_attention_item_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AttentionItem(
            type="preorder_overpaid",
            entity_type="preorder",
            entity_id=1,
            occurred_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
            title="no",
        )


def test_attention_queue_counts_default_zero() -> None:
    queue = AttentionQueue(items=[], counts=AttentionCounts())
    assert queue.items == []
    assert queue.counts.preorder_overpaid == 0
    assert queue.counts.preorder_needs_supplier_order == 0


def test_attention_overpaid_keeps_negative_outstanding() -> None:
    item = AttentionItem(
        type="preorder_overpaid",
        entity_type="preorder",
        entity_id=1,
        occurred_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        outstanding_balance=Decimal("-10.00"),
    )
    assert item.outstanding_balance == Decimal("-10.00")
