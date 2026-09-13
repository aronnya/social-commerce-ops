import pytest
from sqlalchemy.orm import Session

from app.schemas import (
    CustomerCreate,
    EnquiryCreate,
    EnquiryUpdate,
    ProductCreate,
    SupplierCreate,
)
from app.services import (
    NotFoundError,
    create_customer,
    create_enquiry,
    create_product,
    create_supplier,
    delete_enquiry,
    get_enquiry,
    list_enquiries,
    update_enquiry,
)


def _catalogue(db: Session) -> tuple[int, int]:
    supplier = create_supplier(db, SupplierCreate(name="Demo Enquiry Supplier"))
    product = create_product(
        db,
        ProductCreate(supplier_id=supplier.id, name="Demo Enquiry Dress"),
    )
    customer = create_customer(db, CustomerCreate(name="Demo Enquiry Customer"))
    return customer.id, product.id


def test_create_enquiry_with_valid_customer_and_product(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    assert enquiry.customer_id == customer_id
    assert enquiry.product_id == product_id
    assert enquiry.quantity == 1
    assert enquiry.outcome is None
    assert enquiry.enquired_at is not None


def test_create_enquiry_missing_customer_raises(db_session: Session) -> None:
    _, product_id = _catalogue(db_session)
    with pytest.raises(NotFoundError):
        create_enquiry(
            db_session,
            EnquiryCreate(customer_id=999999, product_id=product_id),
        )


def test_create_enquiry_missing_product_raises(db_session: Session) -> None:
    customer_id, _ = _catalogue(db_session)
    with pytest.raises(NotFoundError):
        create_enquiry(
            db_session,
            EnquiryCreate(customer_id=customer_id, product_id=999999),
        )


def test_get_missing_enquiry_raises(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        get_enquiry(db_session, 999999)


def test_update_enquiry_outcome(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    updated = update_enquiry(
        db_session,
        enquiry.id,
        EnquiryUpdate(outcome="TOO_EXPENSIVE"),
    )
    assert updated.outcome == "TOO_EXPENSIVE"
    assert updated.customer_id == customer_id
    assert updated.product_id == product_id


def test_update_enquiry_clears_outcome(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(
            customer_id=customer_id,
            product_id=product_id,
            outcome="CUSTOMER_GHOSTED",
        ),
    )
    updated = update_enquiry(db_session, enquiry.id, EnquiryUpdate(outcome=None))
    assert updated.outcome is None


def test_delete_enquiry(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    delete_enquiry(db_session, enquiry.id)
    with pytest.raises(NotFoundError):
        get_enquiry(db_session, enquiry.id)


def test_list_enquiries_filters(db_session: Session) -> None:
    supplier = create_supplier(db_session, SupplierCreate(name="Demo Filter Supplier"))
    product_a = create_product(
        db_session,
        ProductCreate(supplier_id=supplier.id, name="Demo Dress A"),
    )
    product_b = create_product(
        db_session,
        ProductCreate(supplier_id=supplier.id, name="Demo Dress B"),
    )
    customer_a = create_customer(db_session, CustomerCreate(name="Demo Customer A"))
    customer_b = create_customer(db_session, CustomerCreate(name="Demo Customer B"))

    create_enquiry(
        db_session,
        EnquiryCreate(
            customer_id=customer_a.id,
            product_id=product_a.id,
            outcome="TOO_EXPENSIVE",
        ),
    )
    create_enquiry(
        db_session,
        EnquiryCreate(
            customer_id=customer_b.id,
            product_id=product_b.id,
            outcome="WRONG_SIZE",
        ),
    )
    create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_a.id, product_id=product_b.id),
    )

    by_customer = list_enquiries(db_session, customer_id=customer_a.id)
    assert {item.product_id for item in by_customer} == {product_a.id, product_b.id}

    by_product = list_enquiries(db_session, product_id=product_b.id)
    assert {item.customer_id for item in by_product} == {customer_a.id, customer_b.id}

    by_outcome = list_enquiries(db_session, outcome="TOO_EXPENSIVE")
    assert [item.customer_id for item in by_outcome] == [customer_a.id]
