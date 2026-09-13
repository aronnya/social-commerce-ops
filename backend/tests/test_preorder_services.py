from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.schemas import (
    CustomerCreate,
    EnquiryCreate,
    PreorderCreate,
    PreorderTransition,
    PreorderUpdate,
    ProductCreate,
    SupplierCreate,
)
from app.services import (
    ConflictError,
    NotFoundError,
    create_customer,
    create_enquiry,
    create_preorder,
    create_product,
    create_supplier,
    delete_customer,
    delete_product,
    get_enquiry,
    get_preorder,
    list_preorders,
    transition_preorder,
    update_preorder,
)


def _catalogue(
    db: Session, *, selling_price: Decimal | None = Decimal("85.00")
) -> tuple[int, int]:
    supplier = create_supplier(db, SupplierCreate(name="Demo Preorder Supplier"))
    product = create_product(
        db,
        ProductCreate(
            supplier_id=supplier.id,
            name="Demo Preorder Dress",
            selling_price=selling_price,
        ),
    )
    customer = create_customer(db, CustomerCreate(name="Demo Preorder Customer"))
    return customer.id, product.id


def test_create_walk_in_preorder_starts_confirmed(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    assert preorder.enquiry_id is None
    assert preorder.status == "CONFIRMED"
    assert preorder.quantity == 1
    assert preorder.agreed_price == Decimal("85.00")


def test_create_preorder_null_product_price_leaves_agreed_price_null(
    db_session: Session,
) -> None:
    customer_id, product_id = _catalogue(db_session, selling_price=None)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    assert preorder.agreed_price is None


def test_create_preorder_from_enquiry(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id, quantity=3),
    )
    preorder = create_preorder(
        db_session,
        PreorderCreate(
            customer_id=customer_id,
            product_id=product_id,
            enquiry_id=enquiry.id,
        ),
    )
    assert preorder.enquiry_id == enquiry.id
    assert preorder.quantity == 3
    assert preorder.status == "CONFIRMED"
    assert get_enquiry(db_session, enquiry.id).outcome == "PREORDERED"


def test_second_preorder_for_same_enquiry_conflicts(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    create_preorder(
        db_session,
        PreorderCreate(
            customer_id=customer_id,
            product_id=product_id,
            enquiry_id=enquiry.id,
        ),
    )
    with pytest.raises(ConflictError):
        create_preorder(
            db_session,
            PreorderCreate(
                customer_id=customer_id,
                product_id=product_id,
                enquiry_id=enquiry.id,
            ),
        )


def test_create_preorder_mismatched_enquiry_customer(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    other = create_customer(db_session, CustomerCreate(name="Demo Other Preorder Customer"))
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    with pytest.raises(ConflictError):
        create_preorder(
            db_session,
            PreorderCreate(
                customer_id=other.id,
                product_id=product_id,
                enquiry_id=enquiry.id,
            ),
        )


def test_create_preorder_mismatched_enquiry_product(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    other_product = create_product(
        db_session,
        ProductCreate(
            supplier_id=create_supplier(
                db_session, SupplierCreate(name="Demo Other Preorder Supplier")
            ).id,
            name="Demo Other Preorder Dress",
        ),
    )
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    with pytest.raises(ConflictError):
        create_preorder(
            db_session,
            PreorderCreate(
                customer_id=customer_id,
                product_id=other_product.id,
                enquiry_id=enquiry.id,
            ),
        )


def test_create_preorder_missing_customer(db_session: Session) -> None:
    _, product_id = _catalogue(db_session)
    with pytest.raises(NotFoundError):
        create_preorder(
            db_session,
            PreorderCreate(customer_id=999999, product_id=product_id),
        )


def test_create_preorder_missing_product(db_session: Session) -> None:
    customer_id, _ = _catalogue(db_session)
    with pytest.raises(NotFoundError):
        create_preorder(
            db_session,
            PreorderCreate(customer_id=customer_id, product_id=999999),
        )


def test_create_preorder_missing_enquiry(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    with pytest.raises(NotFoundError):
        create_preorder(
            db_session,
            PreorderCreate(
                customer_id=customer_id,
                product_id=product_id,
                enquiry_id=999999,
            ),
        )


def test_update_preorder_while_confirmed(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    updated = update_preorder(
        db_session,
        preorder.id,
        PreorderUpdate(quantity=2, agreed_price=Decimal("90.00"), notes="hold"),
    )
    assert updated.quantity == 2
    assert updated.agreed_price == Decimal("90.00")
    assert updated.notes == "hold"


def test_update_notes_after_leaving_confirmed(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    transition_preorder(db_session, preorder.id, PreorderTransition(status="CANCELLED"))
    updated = update_preorder(db_session, preorder.id, PreorderUpdate(notes="cancelled in chat"))
    assert updated.notes == "cancelled in chat"


def test_update_quantity_after_leaving_confirmed_conflicts(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    transition_preorder(db_session, preorder.id, PreorderTransition(status="CANCELLED"))
    with pytest.raises(ConflictError):
        update_preorder(db_session, preorder.id, PreorderUpdate(quantity=4))


def test_update_agreed_price_after_leaving_confirmed_conflicts(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    transition_preorder(db_session, preorder.id, PreorderTransition(status="CANCELLED"))
    with pytest.raises(ConflictError):
        update_preorder(
            db_session, preorder.id, PreorderUpdate(agreed_price=Decimal("10.00"))
        )


def test_happy_path_transitions(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    for status in (
        "ORDERED_FROM_SUPPLIER",
        "ARRIVED",
        "READY_FOR_CUSTOMER",
        "FULFILLED",
    ):
        preorder = transition_preorder(
            db_session, preorder.id, PreorderTransition(status=status)
        )
        assert preorder.status == status


def test_confirmed_to_cancelled_and_unavailable(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    first = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    second = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    assert (
        transition_preorder(db_session, first.id, PreorderTransition(status="CANCELLED")).status
        == "CANCELLED"
    )
    assert (
        transition_preorder(
            db_session, second.id, PreorderTransition(status="SUPPLIER_UNAVAILABLE")
        ).status
        == "SUPPLIER_UNAVAILABLE"
    )


def test_illegal_skip_transition(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    with pytest.raises(ConflictError):
        transition_preorder(db_session, preorder.id, PreorderTransition(status="ARRIVED"))


def test_reverse_and_same_state_transitions(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    preorder = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    with pytest.raises(ConflictError):
        transition_preorder(db_session, preorder.id, PreorderTransition(status="CONFIRMED"))
    preorder = transition_preorder(
        db_session, preorder.id, PreorderTransition(status="ORDERED_FROM_SUPPLIER")
    )
    with pytest.raises(ConflictError):
        transition_preorder(db_session, preorder.id, PreorderTransition(status="CONFIRMED"))


def test_terminal_states_reject_transitions(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    cancelled = create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    transition_preorder(db_session, cancelled.id, PreorderTransition(status="CANCELLED"))
    with pytest.raises(ConflictError):
        transition_preorder(
            db_session, cancelled.id, PreorderTransition(status="CONFIRMED")
        )


def test_delete_customer_with_preorder_conflicts(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    with pytest.raises(ConflictError):
        delete_customer(db_session, customer_id)


def test_delete_product_with_preorder_conflicts(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    create_preorder(
        db_session,
        PreorderCreate(customer_id=customer_id, product_id=product_id),
    )
    with pytest.raises(ConflictError):
        delete_product(db_session, product_id)


def test_get_missing_preorder(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        get_preorder(db_session, 999999)


def test_list_preorder_filters(db_session: Session) -> None:
    customer_id, product_id = _catalogue(db_session)
    other_customer = create_customer(
        db_session, CustomerCreate(name="Demo Filter Preorder Customer")
    )
    enquiry = create_enquiry(
        db_session,
        EnquiryCreate(customer_id=customer_id, product_id=product_id),
    )
    linked = create_preorder(
        db_session,
        PreorderCreate(
            customer_id=customer_id,
            product_id=product_id,
            enquiry_id=enquiry.id,
        ),
    )
    create_preorder(
        db_session,
        PreorderCreate(customer_id=other_customer.id, product_id=product_id),
    )
    transition_preorder(db_session, linked.id, PreorderTransition(status="CANCELLED"))

    by_customer = list_preorders(db_session, customer_id=customer_id)
    assert len(by_customer) == 1
    assert by_customer[0].id == linked.id
    by_status = list_preorders(db_session, status="CONFIRMED")
    assert len(by_status) == 1
    assert by_status[0].customer_id == other_customer.id
    by_enquiry = list_preorders(db_session, enquiry_id=enquiry.id)
    assert [item.id for item in by_enquiry] == [linked.id]
    by_product = list_preorders(db_session, product_id=product_id)
    assert len(by_product) == 2
