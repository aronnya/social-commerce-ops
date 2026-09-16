from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.schemas import (
    CustomerCreate,
    EnquiryCreate,
    EnquiryUpdate,
    LOST_DEMAND_REASONS,
    PreorderCreate,
    ProductCreate,
    ReconciliationLineInput,
    SupplierCreate,
    SupplierOrderReconcile,
    SupplierOrderTransition,
)
from app.services import (
    create_customer,
    create_enquiry,
    create_preorder,
    create_product,
    create_supplier,
    generate_supplier_order_draft,
    get_supplier_order,
    list_demand_analytics,
    place_supplier_order,
    reconcile_supplier_order,
    transition_supplier_order,
    update_enquiry,
)


def _supplier_product_customer(
    db: Session,
    *,
    suffix: str,
    style: str | None = None,
    colour: str | None = None,
    size: str | None = None,
):
    supplier = create_supplier(db, SupplierCreate(name=f"Demand Supplier {suffix}"))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name=f"Demand Dress {suffix}",
            style=style,
            colour=colour,
            size=size,
            selling_price=Decimal("85.00"),
        ),
    )
    customer = create_customer(db, CustomerCreate(name=f"Demand Customer {suffix}"))
    return supplier, product, customer


def _enquiry(db: Session, customer_id: int, product_id: int, **extra):
    return create_enquiry(
        db,
        EnquiryCreate(customer_id=customer_id, product_id=product_id, **extra),
    )


def _arrive(db: Session, order_id: int) -> None:
    place_supplier_order(db, order_id)
    for status in ("CONFIRMED", "DISPATCHED", "ARRIVED"):
        transition_supplier_order(db, order_id, SupplierOrderTransition(status=status))


def test_empty_dataset(db_session: Session) -> None:
    analytics = list_demand_analytics(db_session)
    assert analytics.overview.total_enquiries == 0
    assert analytics.overview.conversion_rate is None
    assert analytics.overview.requested_quantity == 0
    assert [bucket.reason for bucket in analytics.lost_demand] == list(LOST_DEMAND_REASONS)
    assert all(bucket.count == 0 for bucket in analytics.lost_demand)
    assert analytics.products == []
    assert analytics.suppliers == []
    assert analytics.fulfilment.date_basis == "all_time"
    assert analytics.fulfilment.reconciled_order_count == 0
    assert analytics.fulfilment.ordered_quantity == 0


def test_open_only_conversion_rate_is_null(db_session: Session) -> None:
    _, product, customer = _supplier_product_customer(db_session, suffix="Open")
    _enquiry(db_session, customer.id, product.id, quantity=2)
    analytics = list_demand_analytics(db_session)
    assert analytics.overview.total_enquiries == 1
    assert analytics.overview.open_enquiries == 1
    assert analytics.overview.resolved_enquiries == 0
    assert analytics.overview.conversion_rate is None
    assert analytics.overview.requested_quantity == 2
    assert analytics.products[0].conversion_rate is None
    assert analytics.suppliers[0].conversion_rate is None


def test_conversion_denominator_and_five_lost_reasons(db_session: Session) -> None:
    _, product, customer = _supplier_product_customer(db_session, suffix="Lost")
    linked = _enquiry(db_session, customer.id, product.id)
    create_preorder(
        db_session,
        PreorderCreate(
            customer_id=customer.id,
            product_id=product.id,
            enquiry_id=linked.id,
        ),
    )
    for reason in LOST_DEMAND_REASONS:
        _enquiry(db_session, customer.id, product.id, outcome=reason)
    _enquiry(db_session, customer.id, product.id)
    analytics = list_demand_analytics(db_session)
    overview = analytics.overview
    assert overview.converted_enquiries == 1
    assert overview.lost_enquiries == 5
    assert overview.open_enquiries == 1
    assert overview.resolved_enquiries == 6
    assert overview.conversion_rate == Decimal(1) / Decimal(6)
    assert overview.total_enquiries == 7
    assert [bucket.count for bucket in analytics.lost_demand] == [1, 1, 1, 1, 1]
    assert overview.lost_enquiries == sum(bucket.count for bucket in analytics.lost_demand)


def test_linked_preorder_defines_conversion_not_outcome(db_session: Session) -> None:
    _, product, customer = _supplier_product_customer(db_session, suffix="Link")
    _enquiry(db_session, customer.id, product.id, outcome="PREORDERED")
    analytics = list_demand_analytics(db_session)
    assert analytics.overview.converted_enquiries == 0
    assert analytics.overview.unlinked_preordered_outcomes == 1
    assert analytics.overview.lost_enquiries == 0
    assert analytics.overview.resolved_enquiries == 0
    assert analytics.overview.conversion_rate is None


def test_mismatch_outcome_stays_converted(db_session: Session) -> None:
    _, product, customer = _supplier_product_customer(db_session, suffix="Mismatch")
    enquiry = _enquiry(db_session, customer.id, product.id)
    create_preorder(
        db_session,
        PreorderCreate(
            customer_id=customer.id,
            product_id=product.id,
            enquiry_id=enquiry.id,
        ),
    )
    update_enquiry(db_session, enquiry.id, EnquiryUpdate(outcome="TOO_EXPENSIVE"))
    analytics = list_demand_analytics(db_session)
    assert analytics.overview.converted_enquiries == 1
    assert analytics.overview.lost_enquiries == 0
    assert analytics.overview.linked_preorder_outcome_mismatch == 1
    assert analytics.lost_demand[0].count == 0


def test_walk_in_preorder_ignored(db_session: Session) -> None:
    _, product, customer = _supplier_product_customer(db_session, suffix="Walkin")
    _enquiry(db_session, customer.id, product.id, outcome="NOT_INTERESTED")
    create_preorder(
        db_session,
        PreorderCreate(customer_id=customer.id, product_id=product.id),
    )
    analytics = list_demand_analytics(db_session)
    assert analytics.overview.converted_enquiries == 0
    assert analytics.overview.lost_enquiries == 1
    assert analytics.overview.total_enquiries == 1


def test_enquiry_count_quantity_distinct_customers_and_omission(
    db_session: Session,
) -> None:
    supplier_a, product_a, customer_a = _supplier_product_customer(
        db_session, suffix="A", style="Maxi", colour="Red", size="M"
    )
    customer_b = create_customer(db_session, CustomerCreate(name="Demand Customer B"))
    product_quiet = create_product(
        db_session,
        ProductCreate(supplier_id=supplier_a.id, name="Demand Quiet Dress"),
    )
    supplier_idle = create_supplier(db_session, SupplierCreate(name="Demand Idle Supplier"))
    create_product(
        db_session,
        ProductCreate(supplier_id=supplier_idle.id, name="Demand Idle Dress"),
    )
    supplier_b, product_b, customer_c = _supplier_product_customer(db_session, suffix="B")
    _enquiry(db_session, customer_a.id, product_a.id, quantity=3)
    _enquiry(db_session, customer_a.id, product_a.id, quantity=1)
    _enquiry(db_session, customer_b.id, product_a.id, quantity=2)
    _enquiry(db_session, customer_c.id, product_b.id, quantity=1, outcome="WRONG_SIZE")
    analytics = list_demand_analytics(db_session)
    assert analytics.overview.total_enquiries == 4
    assert analytics.overview.requested_quantity == 7
    assert [row.product_id for row in analytics.products] == [product_a.id, product_b.id]
    assert product_quiet.id not in {row.product_id for row in analytics.products}
    top = analytics.products[0]
    assert top.enquiry_count == 3
    assert top.requested_quantity == 6
    assert top.distinct_customers == 2
    assert top.style == "Maxi"
    assert top.colour == "Red"
    assert top.size == "M"
    assert top.supplier_id == supplier_a.id
    assert top.supplier_name == supplier_a.name
    assert [row.supplier_id for row in analytics.suppliers] == [
        supplier_a.id,
        supplier_b.id,
    ]
    assert supplier_idle.id not in {row.supplier_id for row in analytics.suppliers}
    assert analytics.suppliers[0].enquiry_count == 3
    assert analytics.suppliers[0].distinct_customers == 2
    assert analytics.suppliers[0].requested_quantity == 6
    assert analytics.products[1].lost_enquiries == 1
    assert analytics.products[1].conversion_rate == Decimal("0")


def test_product_and_supplier_ordering(db_session: Session) -> None:
    supplier_low, product_low, customer = _supplier_product_customer(
        db_session, suffix="Low"
    )
    supplier_high, product_high_qty, _ = _supplier_product_customer(
        db_session, suffix="High"
    )
    product_high_count = create_product(
        db_session,
        ProductCreate(supplier_id=supplier_high.id, name="Demand Tie Count"),
    )
    _enquiry(db_session, customer.id, product_low.id, quantity=9)
    _enquiry(db_session, customer.id, product_high_count.id, quantity=1)
    _enquiry(db_session, customer.id, product_high_count.id, quantity=1)
    _enquiry(db_session, customer.id, product_high_qty.id, quantity=4)
    _enquiry(db_session, customer.id, product_high_qty.id, quantity=4)
    analytics = list_demand_analytics(db_session)
    assert [row.product_id for row in analytics.products] == [
        product_high_qty.id,
        product_high_count.id,
        product_low.id,
    ]
    assert [row.supplier_id for row in analytics.suppliers] == [
        supplier_high.id,
        supplier_low.id,
    ]


def test_date_range_half_open(db_session: Session) -> None:
    _, product, customer = _supplier_product_customer(db_session, suffix="Dates")
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 4, 10, 0, tzinfo=timezone.utc)
    _enquiry(db_session, customer.id, product.id, enquired_at=t0)
    _enquiry(db_session, customer.id, product.id, enquired_at=t1)
    _enquiry(db_session, customer.id, product.id, enquired_at=t2)
    analytics = list_demand_analytics(db_session, from_=t1, to=t2)
    assert analytics.from_ == t1
    assert analytics.to == t2
    assert analytics.overview.total_enquiries == 1
    with pytest.raises(ValueError, match="from must be earlier than to"):
        list_demand_analytics(db_session, from_=t2, to=t1)
    with pytest.raises(ValueError, match="from must be earlier than to"):
        list_demand_analytics(db_session, from_=t1, to=t1)
    all_but_last = list_demand_analytics(db_session, from_=t0, to=t2)
    assert all_but_last.overview.total_enquiries == 2
    until_t3 = list_demand_analytics(db_session, from_=t0, to=t3)
    assert until_t3.overview.total_enquiries == 3


def test_fulfilment_all_time_exact_shortage_excess_and_excludes_unreconciled(
    db_session: Session,
) -> None:
    supplier, product, customer = _supplier_product_customer(
        db_session, suffix="Recon"
    )
    extra = create_product(
        db_session,
        ProductCreate(
            supplier_id=supplier.id,
            name="Demand Recon Extra",
            selling_price=Decimal("85.00"),
        ),
    )
    early = datetime(2025, 1, 1, tzinfo=timezone.utc)
    _enquiry(db_session, customer.id, product.id, enquired_at=early)
    confirmed = []
    for item in (product, extra, product):
        preorder = create_preorder(
            db_session,
            PreorderCreate(customer_id=customer.id, product_id=item.id),
        )
        confirmed.append(preorder)
    exact = generate_supplier_order_draft(
        db_session, supplier.id, [confirmed[0].id]
    )
    shortage = generate_supplier_order_draft(
        db_session, supplier.id, [confirmed[1].id]
    )
    excess = generate_supplier_order_draft(
        db_session, supplier.id, [confirmed[2].id]
    )
    _arrive(db_session, exact.id)
    _arrive(db_session, shortage.id)
    _arrive(db_session, excess.id)
    arrived_only = generate_supplier_order_draft(
        db_session,
        supplier.id,
        [
            create_preorder(
                db_session,
                PreorderCreate(customer_id=customer.id, product_id=product.id),
            ).id
        ],
    )
    _arrive(db_session, arrived_only.id)

    def _reconcile(order_id: int, received: int) -> None:
        order = get_supplier_order(db_session, order_id)
        reconcile_supplier_order(
            db_session,
            order.id,
            SupplierOrderReconcile(
                lines=[
                    ReconciliationLineInput(
                        line_id=order.lines[0].id,
                        received_quantity=received,
                    )
                ]
            ),
        )

    _reconcile(exact.id, 1)
    _reconcile(shortage.id, 0)
    _reconcile(excess.id, 3)

    window_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    analytics = list_demand_analytics(db_session, from_=window_start)
    assert analytics.overview.total_enquiries == 0
    assert analytics.fulfilment.date_basis == "all_time"
    assert analytics.fulfilment.reconciled_order_count == 3
    assert analytics.fulfilment.ordered_quantity == 3
    assert analytics.fulfilment.received_quantity == 4
    assert analytics.fulfilment.shortage_units == 1
    assert analytics.fulfilment.excess_units == 2
