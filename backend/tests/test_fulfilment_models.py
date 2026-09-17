from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Fulfilment, Preorder, utc_now
from app.schemas import CustomerCreate, PreorderCreate, ProductCreate, SupplierCreate
from app.services import create_customer, create_preorder, create_product, create_supplier


POST_ADDRESS = "Test Recipient\n1 Test Street\nTest Town"


def test_fulfilment_relationship_on_preorder() -> None:
    assert "fulfilment" in Preorder.__mapper__.relationships
    assert "preorder" in Fulfilment.__mapper__.relationships
    assert Fulfilment.__table__.c.preorder_id.nullable is False
    assert Fulfilment.__table__.c.postage_cost.nullable is True


def _preorder(db: Session) -> Preorder:
    supplier = create_supplier(db, SupplierCreate(name="Demo Fulfilment Model Supplier"))
    product = create_product(
        db,
        ProductCreate(supplier_id=supplier.id, name="Demo Fulfilment Model Dress"),
    )
    customer = create_customer(db, CustomerCreate(name="Demo Fulfilment Model Customer"))
    return create_preorder(
        db,
        PreorderCreate(customer_id=customer.id, product_id=product.id),
    )


def test_unique_preorder_fulfilment_and_method_checks(db_session: Session) -> None:
    preorder = _preorder(db_session)
    row = Fulfilment(
        preorder_id=preorder.id,
        method="HOME_COLLECTION",
        fulfilled_at=utc_now(),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.fulfilled_at.tzinfo is not None
    assert preorder.fulfilment.id == row.id
    assert row.preorder.id == preorder.id

    duplicate = Fulfilment(
        preorder_id=preorder.id,
        method="HOME_COLLECTION",
        fulfilled_at=datetime.now(timezone.utc),
    )
    db_session.add(duplicate)
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()


def test_home_collection_rejects_postage_cost_at_db(db_session: Session) -> None:
    preorder = _preorder(db_session)
    db_session.add(
        Fulfilment(
            preorder_id=preorder.id,
            method="HOME_COLLECTION",
            postage_cost=Decimal("1.00"),
            fulfilled_at=utc_now(),
        )
    )
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()


def test_post_regular_allows_null_and_zero_postage_rejects_negative(
    db_session: Session,
) -> None:
    first = _preorder(db_session)
    db_session.add(
        Fulfilment(
            preorder_id=first.id,
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=None,
            fulfilled_at=utc_now(),
        )
    )
    db_session.commit()

    second = _preorder(db_session)
    db_session.add(
        Fulfilment(
            preorder_id=second.id,
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("0"),
            fulfilled_at=utc_now(),
        )
    )
    db_session.commit()

    third = _preorder(db_session)
    db_session.add(
        Fulfilment(
            preorder_id=third.id,
            method="POST",
            postage_type="REGULAR",
            delivery_address=POST_ADDRESS,
            postage_cost=Decimal("-1.00"),
            fulfilled_at=utc_now(),
        )
    )
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()


def test_post_registered_requires_tracking_at_db(db_session: Session) -> None:
    preorder = _preorder(db_session)
    db_session.add(
        Fulfilment(
            preorder_id=preorder.id,
            method="POST",
            postage_type="REGISTERED",
            delivery_address=POST_ADDRESS,
            tracking_reference=None,
            fulfilled_at=utc_now(),
        )
    )
    try:
        db_session.commit()
        raise AssertionError("expected IntegrityError")
    except IntegrityError:
        db_session.rollback()
