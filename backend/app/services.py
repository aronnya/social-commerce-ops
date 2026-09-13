from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Customer,
    Enquiry,
    Payment,
    Preorder,
    Product,
    Supplier,
    SupplierOrder,
    SupplierOrderAllocation,
    SupplierOrderLine,
    utc_now,
)
from app.schemas import (
    CustomerCreate,
    CustomerUpdate,
    EnquiryCreate,
    EnquiryUpdate,
    PaymentCreate,
    PaymentSummary,
    PaymentUpdate,
    PreorderCreate,
    PreorderTransition,
    PreorderUpdate,
    ProductCreate,
    ProductUpdate,
    SupplierCreate,
    SupplierOrderTransition,
    SupplierOrderUpdate,
    SupplierUpdate,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


# ORDERED_FROM_SUPPLIER is set only by place_supplier_order, not public transitions.
PREORDER_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CONFIRMED": frozenset({"CANCELLED", "SUPPLIER_UNAVAILABLE"}),
    "ORDERED_FROM_SUPPLIER": frozenset({"ARRIVED", "CANCELLED", "SUPPLIER_UNAVAILABLE"}),
    "ARRIVED": frozenset({"READY_FOR_CUSTOMER", "SUPPLIER_UNAVAILABLE"}),
    "READY_FOR_CUSTOMER": frozenset({"FULFILLED", "CANCELLED"}),
    "FULFILLED": frozenset(),
    "CANCELLED": frozenset(),
    "SUPPLIER_UNAVAILABLE": frozenset(),
}

# Full machine. DRAFT -> PLACED is owned by place_supplier_order, not the generic transition.
SUPPLIER_ORDER_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PLACED"}),
    "PLACED": frozenset({"CONFIRMED"}),
    "CONFIRMED": frozenset({"DISPATCHED"}),
    "DISPATCHED": frozenset({"ARRIVED"}),
    "ARRIVED": frozenset({"RECONCILED"}),
    "RECONCILED": frozenset(),
}


def list_suppliers(db: Session) -> list[Supplier]:
    return list(db.scalars(select(Supplier).order_by(Supplier.id)).all())


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {supplier_id} was not found.")
    return supplier


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier_id: int, data: SupplierUpdate) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_supplier(db: Session, supplier_id: int) -> None:
    supplier = get_supplier(db, supplier_id)
    product_count = db.scalar(
        select(Product.id).where(Product.supplier_id == supplier_id).limit(1)
    )
    if product_count is not None:
        raise ConflictError(
            "This supplier still has catalogue products. Remove or reassign them first."
        )
    order_id = db.scalar(
        select(SupplierOrder.id).where(SupplierOrder.supplier_id == supplier_id).limit(1)
    )
    if order_id is not None:
        raise ConflictError(
            "This supplier still has supplier orders. Remove them first."
        )
    db.delete(supplier)
    db.commit()


def list_products(db: Session, supplier_id: int | None = None) -> list[Product]:
    statement = select(Product).order_by(Product.id)
    if supplier_id is not None:
        statement = statement.where(Product.supplier_id == supplier_id)
    return list(db.scalars(statement).all())


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} was not found.")
    return product


def create_product(db: Session, data: ProductCreate) -> Product:
    get_supplier(db, data.supplier_id)
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    updates = data.model_dump(exclude_unset=True)
    if "supplier_id" in updates:
        get_supplier(db, updates["supplier_id"])
        if updates["supplier_id"] != product.supplier_id:
            line_id = db.scalar(
                select(SupplierOrderLine.id)
                .where(SupplierOrderLine.product_id == product.id)
                .limit(1)
            )
            if line_id is not None:
                raise ConflictError(
                    "This product is on a supplier order and cannot change supplier."
                )
    for field, value in updates.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int) -> None:
    product = get_product(db, product_id)
    enquiry_id = db.scalar(select(Enquiry.id).where(Enquiry.product_id == product_id).limit(1))
    if enquiry_id is not None:
        raise ConflictError(
            "This product still has enquiries. Remove them first."
        )
    preorder_id = db.scalar(select(Preorder.id).where(Preorder.product_id == product_id).limit(1))
    if preorder_id is not None:
        raise ConflictError(
            "This product still has preorders. Cancel them first."
        )
    db.delete(product)
    db.commit()


def list_customers(db: Session) -> list[Customer]:
    return list(db.scalars(select(Customer).order_by(Customer.id)).all())


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError(f"Customer {customer_id} was not found.")
    return customer


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    customer = Customer(**data.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(db: Session, customer_id: int, data: CustomerUpdate) -> Customer:
    customer = get_customer(db, customer_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(db: Session, customer_id: int) -> None:
    customer = get_customer(db, customer_id)
    enquiry_id = db.scalar(
        select(Enquiry.id).where(Enquiry.customer_id == customer_id).limit(1)
    )
    if enquiry_id is not None:
        raise ConflictError(
            "This customer still has enquiries. Remove them first."
        )
    preorder_id = db.scalar(
        select(Preorder.id).where(Preorder.customer_id == customer_id).limit(1)
    )
    if preorder_id is not None:
        raise ConflictError(
            "This customer still has preorders. Cancel them first."
        )
    db.delete(customer)
    db.commit()


def list_enquiries(
    db: Session,
    customer_id: int | None = None,
    product_id: int | None = None,
    outcome: str | None = None,
    open_only: bool = False,
) -> list[Enquiry]:
    statement = select(Enquiry).order_by(Enquiry.id)
    if customer_id is not None:
        statement = statement.where(Enquiry.customer_id == customer_id)
    if product_id is not None:
        statement = statement.where(Enquiry.product_id == product_id)
    if open_only:
        statement = statement.where(Enquiry.outcome.is_(None))
    elif outcome is not None:
        statement = statement.where(Enquiry.outcome == outcome)
    return list(db.scalars(statement).all())


def get_enquiry(db: Session, enquiry_id: int) -> Enquiry:
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise NotFoundError(f"Enquiry {enquiry_id} was not found.")
    return enquiry


def create_enquiry(db: Session, data: EnquiryCreate) -> Enquiry:
    get_customer(db, data.customer_id)
    get_product(db, data.product_id)
    enquiry = Enquiry(**data.model_dump(exclude_unset=True))
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)
    return enquiry


def update_enquiry(db: Session, enquiry_id: int, data: EnquiryUpdate) -> Enquiry:
    enquiry = get_enquiry(db, enquiry_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(enquiry, field, value)
    db.commit()
    db.refresh(enquiry)
    return enquiry


def delete_enquiry(db: Session, enquiry_id: int) -> None:
    enquiry = get_enquiry(db, enquiry_id)
    db.delete(enquiry)
    db.commit()


def list_preorders(
    db: Session,
    customer_id: int | None = None,
    product_id: int | None = None,
    status: str | None = None,
    enquiry_id: int | None = None,
) -> list[Preorder]:
    statement = select(Preorder).order_by(Preorder.id)
    if customer_id is not None:
        statement = statement.where(Preorder.customer_id == customer_id)
    if product_id is not None:
        statement = statement.where(Preorder.product_id == product_id)
    if status is not None:
        statement = statement.where(Preorder.status == status)
    if enquiry_id is not None:
        statement = statement.where(Preorder.enquiry_id == enquiry_id)
    return list(db.scalars(statement).all())


def get_preorder(db: Session, preorder_id: int) -> Preorder:
    preorder = db.get(Preorder, preorder_id)
    if preorder is None:
        raise NotFoundError(f"Preorder {preorder_id} was not found.")
    return preorder


def create_preorder(db: Session, data: PreorderCreate) -> Preorder:
    get_customer(db, data.customer_id)
    product = get_product(db, data.product_id)

    enquiry = None
    if data.enquiry_id is not None:
        enquiry = get_enquiry(db, data.enquiry_id)
        if enquiry.customer_id != data.customer_id or enquiry.product_id != data.product_id:
            raise ConflictError(
                "The enquiry must be for the same customer and product as the preorder."
            )
        existing = db.scalar(
            select(Preorder.id).where(Preorder.enquiry_id == enquiry.id).limit(1)
        )
        if existing is not None:
            raise ConflictError("This enquiry already has a preorder.")

    fields_set = data.model_fields_set
    payload = data.model_dump(exclude_unset=True)
    if "quantity" in fields_set:
        quantity = payload["quantity"]
    elif enquiry is not None:
        quantity = enquiry.quantity
    else:
        quantity = 1

    if "agreed_price" in fields_set:
        agreed_price = payload["agreed_price"]
    else:
        agreed_price = product.selling_price

    preorder = Preorder(
        customer_id=data.customer_id,
        product_id=data.product_id,
        enquiry_id=data.enquiry_id,
        quantity=quantity,
        status="CONFIRMED",
        agreed_price=agreed_price,
        notes=payload.get("notes", data.notes),
    )
    db.add(preorder)
    if enquiry is not None:
        enquiry.outcome = "PREORDERED"
    db.commit()
    db.refresh(preorder)
    return preorder


def update_preorder(db: Session, preorder_id: int, data: PreorderUpdate) -> Preorder:
    preorder = get_preorder(db, preorder_id)
    updates = data.model_dump(exclude_unset=True)
    changing_price_or_qty = "quantity" in updates or "agreed_price" in updates
    if changing_price_or_qty and preorder.status != "CONFIRMED":
        raise ConflictError(
            "Quantity and agreed price can only be changed while the preorder is CONFIRMED."
        )
    if changing_price_or_qty:
        payment_id = db.scalar(
            select(Payment.id).where(Payment.preorder_id == preorder.id).limit(1)
        )
        if payment_id is not None:
            raise ConflictError(
                "Quantity and agreed price cannot be changed after a payment has been recorded."
            )
    if "quantity" in updates:
        allocation_id = db.scalar(
            select(SupplierOrderAllocation.id)
            .where(SupplierOrderAllocation.preorder_id == preorder.id)
            .limit(1)
        )
        if allocation_id is not None:
            raise ConflictError(
                "Quantity cannot be changed after the preorder is on a supplier order."
            )
    for field, value in updates.items():
        setattr(preorder, field, value)
    db.commit()
    db.refresh(preorder)
    return preorder


def transition_preorder(
    db: Session, preorder_id: int, data: PreorderTransition
) -> Preorder:
    preorder = get_preorder(db, preorder_id)
    allowed = PREORDER_ALLOWED_TRANSITIONS.get(preorder.status, frozenset())
    if data.status == preorder.status or data.status not in allowed:
        raise ConflictError(
            f"Cannot transition preorder from {preorder.status} to {data.status}."
        )
    preorder.status = data.status
    db.commit()
    db.refresh(preorder)
    return preorder


def _amount_paid(db: Session, preorder_id: int) -> Decimal:
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.preorder_id == preorder_id
        )
    )
    return Decimal(paid)


def list_payments(db: Session, preorder_id: int) -> list[Payment]:
    get_preorder(db, preorder_id)
    statement = (
        select(Payment)
        .where(Payment.preorder_id == preorder_id)
        .order_by(Payment.paid_at, Payment.id)
    )
    return list(db.scalars(statement).all())


def get_payment(db: Session, preorder_id: int, payment_id: int) -> Payment:
    get_preorder(db, preorder_id)
    payment = db.get(Payment, payment_id)
    if payment is None or payment.preorder_id != preorder_id:
        raise NotFoundError(f"Payment {payment_id} was not found.")
    return payment


def create_payment(db: Session, preorder_id: int, data: PaymentCreate) -> Payment:
    preorder = get_preorder(db, preorder_id)
    if preorder.agreed_price is None:
        raise ConflictError("Set agreed_price on the preorder before recording a payment.")
    payload = data.model_dump(exclude_unset=True)
    payment = Payment(preorder_id=preorder.id, **payload)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    db.refresh(preorder)
    return payment


def update_payment(
    db: Session, preorder_id: int, payment_id: int, data: PaymentUpdate
) -> Payment:
    payment = get_payment(db, preorder_id, payment_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(payment, field, value)
    db.commit()
    db.refresh(payment)
    return payment


def payment_summary(db: Session, preorder: Preorder) -> PaymentSummary:
    amount_paid = _amount_paid(db, preorder.id)
    if preorder.agreed_price is None:
        return PaymentSummary(
            total_amount=None,
            amount_paid=amount_paid,
            outstanding_balance=None,
            status=None,
        )
    total_amount = Decimal(preorder.quantity) * Decimal(preorder.agreed_price)
    outstanding = total_amount - amount_paid
    if amount_paid > total_amount:
        status = "OVERPAID"
    elif amount_paid == total_amount:
        status = "PAID"
    elif amount_paid == 0:
        status = "UNPAID"
    else:
        status = "PARTIALLY_PAID"
    return PaymentSummary(
        total_amount=total_amount,
        amount_paid=amount_paid,
        outstanding_balance=outstanding,
        status=status,
    )


def _supplier_order_load_options():
    return (
        selectinload(SupplierOrder.lines).selectinload(SupplierOrderLine.allocations),
        selectinload(SupplierOrder.lines).selectinload(SupplierOrderLine.product),
    )


def _get_supplier_order_loaded(db: Session, supplier_order_id: int) -> SupplierOrder:
    statement = (
        select(SupplierOrder)
        .options(*_supplier_order_load_options())
        .where(SupplierOrder.id == supplier_order_id)
    )
    order = db.scalars(statement).unique().one_or_none()
    if order is None:
        raise NotFoundError(f"Supplier order {supplier_order_id} was not found.")
    return order


def _lock_preorders(db: Session, preorder_ids: list[int]) -> list[Preorder]:
    if not preorder_ids:
        return []
    statement = (
        select(Preorder)
        .where(Preorder.id.in_(preorder_ids))
        .order_by(Preorder.id)
        .with_for_update()
    )
    locked = list(db.scalars(statement).all())
    for preorder in locked:
        _ = preorder.product
        _ = preorder.supplier_order_allocation
    return locked


def _eligible_preorder_ids_for_supplier(db: Session, supplier_id: int) -> list[int]:
    allocated = select(SupplierOrderAllocation.preorder_id)
    statement = (
        select(Preorder.id)
        .join(Product, Preorder.product_id == Product.id)
        .where(Preorder.status == "CONFIRMED")
        .where(Product.supplier_id == supplier_id)
        .where(Preorder.id.not_in(allocated))
        .order_by(Preorder.id)
    )
    return list(db.scalars(statement).all())


def _assert_preorder_eligible(
    preorder: Preorder, supplier_id: int
) -> None:
    if preorder.status != "CONFIRMED":
        raise ConflictError(
            f"Preorder {preorder.id} must be CONFIRMED to include on a supplier order."
        )
    if preorder.product.supplier_id != supplier_id:
        raise ConflictError(
            f"Preorder {preorder.id} does not belong to supplier {supplier_id}."
        )
    if preorder.supplier_order_allocation is not None:
        raise ConflictError(
            f"Preorder {preorder.id} is already allocated to a supplier order."
        )


def _raise_if_allocation_integrity_error(exc: IntegrityError) -> None:
    message = str(getattr(exc, "orig", exc)).lower()
    if (
        "supplier_order_allocations" in message
        or "ix_supplier_order_allocations_preorder_id" in message
    ):
        raise ConflictError(
            "This preorder is already allocated to a supplier order."
        ) from exc


def list_supplier_orders(
    db: Session,
    supplier_id: int | None = None,
    status: str | None = None,
) -> list[SupplierOrder]:
    statement = (
        select(SupplierOrder)
        .options(*_supplier_order_load_options())
        .order_by(SupplierOrder.id)
    )
    if supplier_id is not None:
        statement = statement.where(SupplierOrder.supplier_id == supplier_id)
    if status is not None:
        statement = statement.where(SupplierOrder.status == status)
    return list(db.scalars(statement).unique().all())


def get_supplier_order(db: Session, supplier_order_id: int) -> SupplierOrder:
    return _get_supplier_order_loaded(db, supplier_order_id)


def generate_supplier_order_draft(
    db: Session,
    supplier_id: int,
    preorder_ids: list[int] | None,
) -> SupplierOrder:
    get_supplier(db, supplier_id)
    if preorder_ids is None:
        candidate_ids = _eligible_preorder_ids_for_supplier(db, supplier_id)
    else:
        candidate_ids = list(dict.fromkeys(preorder_ids))

    locked = _lock_preorders(db, candidate_ids)
    locked_by_id = {preorder.id: preorder for preorder in locked}

    if preorder_ids is not None:
        for preorder_id in candidate_ids:
            if preorder_id not in locked_by_id:
                raise NotFoundError(f"Preorder {preorder_id} was not found.")
        for preorder in locked:
            _assert_preorder_eligible(preorder, supplier_id)
    else:
        eligible = []
        for preorder in locked:
            try:
                _assert_preorder_eligible(preorder, supplier_id)
            except ConflictError:
                continue
            eligible.append(preorder)
        locked = eligible

    if not locked:
        raise ConflictError("No eligible confirmed preorders for this supplier.")

    grouped: dict[int, list[Preorder]] = {}
    for preorder in locked:
        grouped.setdefault(preorder.product_id, []).append(preorder)

    order = SupplierOrder(supplier_id=supplier_id, status="DRAFT", placed_at=None)
    db.add(order)
    try:
        db.flush()
        for product_id in grouped:
            group = grouped[product_id]
            line = SupplierOrderLine(
                supplier_order_id=order.id,
                product_id=product_id,
                quantity=sum(item.quantity for item in group),
                unit_cost=group[0].product.supplier_cost,
            )
            db.add(line)
            db.flush()
            for item in group:
                db.add(
                    SupplierOrderAllocation(
                        supplier_order_line_id=line.id,
                        preorder_id=item.id,
                        quantity=item.quantity,
                    )
                )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_allocation_integrity_error(exc)
        raise
    return _get_supplier_order_loaded(db, order.id)


def update_supplier_order(
    db: Session, supplier_order_id: int, data: SupplierOrderUpdate
) -> SupplierOrder:
    order = get_supplier_order(db, supplier_order_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    db.commit()
    return _get_supplier_order_loaded(db, order.id)


def delete_supplier_order_draft(db: Session, supplier_order_id: int) -> None:
    order = get_supplier_order(db, supplier_order_id)
    if order.status != "DRAFT":
        raise ConflictError("Only DRAFT supplier orders can be deleted.")
    for line in list(order.lines):
        for allocation in list(line.allocations):
            db.delete(allocation)
        db.delete(line)
    db.delete(order)
    db.commit()


def place_supplier_order(db: Session, supplier_order_id: int) -> SupplierOrder:
    order = get_supplier_order(db, supplier_order_id)
    if order.status != "DRAFT":
        raise ConflictError("Only a DRAFT supplier order can be placed.")
    allocations = [allocation for line in order.lines for allocation in line.allocations]
    if not order.lines or not allocations:
        raise ConflictError("A supplier order must have lines and allocations before placing.")

    locked = _lock_preorders(db, [allocation.preorder_id for allocation in allocations])
    locked_by_id = {preorder.id: preorder for preorder in locked}
    line_ids = {line.id for line in order.lines}

    for line in order.lines:
        allocated_qty = sum(allocation.quantity for allocation in line.allocations)
        if allocated_qty != line.quantity:
            raise ConflictError(
                f"Supplier order line {line.id} quantity does not match its allocations."
            )

    for allocation in allocations:
        preorder = locked_by_id.get(allocation.preorder_id)
        if preorder is None:
            raise ConflictError(
                f"Preorder {allocation.preorder_id} was not found for this supplier order."
            )
        if preorder.status != "CONFIRMED":
            raise ConflictError(
                f"Preorder {preorder.id} must be CONFIRMED to place the supplier order."
            )
        linked = preorder.supplier_order_allocation
        if linked is None or linked.supplier_order_line_id not in line_ids:
            raise ConflictError(
                f"Preorder {preorder.id} is not allocated to this supplier order."
            )
        if allocation.quantity != preorder.quantity:
            raise ConflictError(
                f"Allocation quantity for preorder {preorder.id} does not match the preorder."
            )

    order.status = "PLACED"
    order.placed_at = utc_now()
    for preorder in locked:
        preorder.status = "ORDERED_FROM_SUPPLIER"
    db.commit()
    return _get_supplier_order_loaded(db, order.id)


def transition_supplier_order(
    db: Session, supplier_order_id: int, data: SupplierOrderTransition
) -> SupplierOrder:
    order = get_supplier_order(db, supplier_order_id)
    if data.status == "PLACED" or order.status == "DRAFT":
        raise ConflictError(
            "Placing a supplier order must use place_supplier_order."
        )
    allowed = SUPPLIER_ORDER_ALLOWED_TRANSITIONS.get(order.status, frozenset())
    if data.status == order.status or data.status not in allowed:
        raise ConflictError(
            f"Cannot transition supplier order from {order.status} to {data.status}."
        )
    order.status = data.status
    db.commit()
    return _get_supplier_order_loaded(db, order.id)
