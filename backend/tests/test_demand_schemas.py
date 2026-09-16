from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import (
    DemandAnalytics,
    DemandOverview,
    FulfilmentSnapshot,
    LOST_DEMAND_REASONS,
    LostDemandBucket,
    ProductDemandRow,
    SupplierDemandRow,
)


def _empty_analytics(**extra) -> DemandAnalytics:
    return DemandAnalytics(
        overview=DemandOverview(),
        lost_demand=[
            LostDemandBucket(reason=reason, count=0) for reason in LOST_DEMAND_REASONS
        ],
        products=[],
        suppliers=[],
        fulfilment=FulfilmentSnapshot(),
        **extra,
    )


def test_demand_overview_defaults_and_null_rate() -> None:
    overview = DemandOverview()
    assert overview.total_enquiries == 0
    assert overview.resolved_enquiries == 0
    assert overview.conversion_rate is None
    assert overview.unlinked_preordered_outcomes == 0
    assert overview.linked_preorder_outcome_mismatch == 0


def test_demand_overview_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DemandOverview(revenue="no")


def test_lost_demand_reasons_are_stable() -> None:
    assert LOST_DEMAND_REASONS == (
        "TOO_EXPENSIVE",
        "SUPPLIER_UNAVAILABLE",
        "CUSTOMER_GHOSTED",
        "WRONG_SIZE",
        "NOT_INTERESTED",
    )
    with pytest.raises(ValidationError):
        LostDemandBucket(reason="PREORDERED", count=1)


def test_fulfilment_date_basis_is_all_time() -> None:
    snap = FulfilmentSnapshot()
    assert snap.date_basis == "all_time"
    with pytest.raises(ValidationError):
        FulfilmentSnapshot(date_basis="enquired_at")


def test_demand_analytics_accepts_from_alias() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    payload = _empty_analytics(from_=start)
    assert payload.from_ == start
    dumped = payload.model_dump(by_alias=True)
    assert dumped["from"] == start
    assert dumped["to"] is None


def test_product_and_supplier_rows_reject_score_fields() -> None:
    with pytest.raises(ValidationError):
        ProductDemandRow(
            product_id=1,
            name="Dress",
            style=None,
            colour=None,
            size=None,
            supplier_id=1,
            supplier_name="S",
            enquiry_count=1,
            distinct_customers=1,
            requested_quantity=1,
            converted_enquiries=0,
            lost_enquiries=0,
            open_enquiries=1,
            high_interest=True,
        )
    with pytest.raises(ValidationError):
        SupplierDemandRow(
            supplier_id=1,
            name="S",
            enquiry_count=1,
            distinct_customers=1,
            requested_quantity=1,
            converted_enquiries=0,
            lost_enquiries=0,
            open_enquiries=1,
            conversion_rate=Decimal("0.5"),
            quality_score=1,
        )
