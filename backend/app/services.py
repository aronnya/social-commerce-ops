from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Customer,
    Enquiry,
    InventoryLot,
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
    AttentionCounts,
    AttentionItem,
    AttentionQueue,
    CustomerCreate,
    CustomerUpdate,
    DemandAnalytics,
    DemandOverview,
    EnquiryCreate,
    EnquiryUpdate,
    FulfilmentSnapshot,
    LOST_DEMAND_REASONS,
    LostDemandBucket,
    PaymentCreate,
    PaymentSummary,
    PaymentUpdate,
    PreorderCreate,
    PreorderTransition,
    PreorderUpdate,
    ProductCreate,
    ProductDemandRow,
    ProductUpdate,
    SupplierCreate,
    SupplierDemandRow,
    SupplierOrderReconcile,
    SupplierOrderTransition,
    SupplierOrderUpdate,
    SupplierUpdate,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


# ORDERED_FROM_SUPPLIER is set only by place_supplier_order.
# ARRIVED for allocated preorders is set only by reconcile_supplier_order.
PREORDER_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CONFIRMED": frozenset({"CANCELLED", "SUPPLIER_UNAVAILABLE"}),
    "ORDERED_FROM_SUPPLIER": frozenset({"CANCELLED", "SUPPLIER_UNAVAILABLE"}),
    "ARRIVED": frozenset({"READY_FOR_CUSTOMER", "SUPPLIER_UNAVAILABLE"}),
    "READY_FOR_CUSTOMER": frozenset({"FULFILLED", "CANCELLED"}),
    "FULFILLED": frozenset(),
    "CANCELLED": frozenset(),
    "SUPPLIER_UNAVAILABLE": frozenset(),
}

# Full machine. PLACED and RECONCILED are owned by dedicated operations.
SUPPLIER_ORDER_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PLACED"}),
    "PLACED": frozenset({"CONFIRMED"}),
    "CONFIRMED": frozenset({"DISPATCHED"}),
    "DISPATCHED": frozenset({"ARRIVED"}),
    "ARRIVED": frozenset(),
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
    lot_id = db.scalar(
        select(InventoryLot.id).where(InventoryLot.product_id == product_id).limit(1)
    )
    if lot_id is not None:
        raise ConflictError(
            "This product still has inventory lots. Remove them first."
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


def _raise_if_inventory_lot_integrity_error(exc: IntegrityError) -> None:
    message = str(getattr(exc, "orig", exc)).lower()
    if (
        "inventory_lots" in message
        or "ix_inventory_lots_supplier_order_line_id" in message
    ):
        raise ConflictError(
            "Inventory has already been recorded for this supplier order line."
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
    if data.status == "PLACED" or data.status == "RECONCILED" or order.status == "DRAFT":
        raise ConflictError(
            "Placing or reconciling a supplier order must use the dedicated operation."
        )
    allowed = SUPPLIER_ORDER_ALLOWED_TRANSITIONS.get(order.status, frozenset())
    if data.status == order.status or data.status not in allowed:
        raise ConflictError(
            f"Cannot transition supplier order from {order.status} to {data.status}."
        )
    order.status = data.status
    db.commit()
    return _get_supplier_order_loaded(db, order.id)


def _lock_supplier_order(db: Session, supplier_order_id: int) -> SupplierOrder:
    statement = (
        select(SupplierOrder)
        .where(SupplierOrder.id == supplier_order_id)
        .with_for_update()
    )
    order = db.scalars(statement).one_or_none()
    if order is None:
        raise NotFoundError(f"Supplier order {supplier_order_id} was not found.")
    return order


def _fifo_complete_preorders(preorders: list[Preorder], received_quantity: int) -> list[Preorder]:
    remaining = received_quantity
    selected: list[Preorder] = []
    for preorder in preorders:
        if remaining >= preorder.quantity:
            selected.append(preorder)
            remaining -= preorder.quantity
        else:
            break
    return selected


def reconcile_supplier_order(
    db: Session, supplier_order_id: int, data: SupplierOrderReconcile
) -> SupplierOrder:
    order = _lock_supplier_order(db, supplier_order_id)
    if order.status != "ARRIVED" or order.reconciled_at is not None:
        raise ConflictError("Only an unreconciled ARRIVED supplier order can be reconciled.")

    lines = list(
        db.scalars(
            select(SupplierOrderLine)
            .where(SupplierOrderLine.supplier_order_id == order.id)
            .order_by(SupplierOrderLine.id)
            .with_for_update()
        ).all()
    )
    if not lines:
        raise ConflictError("A supplier order must have lines before reconciling.")
    lines_by_id = {line.id: line for line in lines}
    request_ids = [item.line_id for item in data.lines]
    if set(request_ids) != set(lines_by_id):
        missing = set(lines_by_id) - set(request_ids)
        extra = set(request_ids) - set(lines_by_id)
        if extra:
            extra_id = next(iter(extra))
            other = db.get(SupplierOrderLine, extra_id)
            if other is None:
                raise NotFoundError(f"Supplier order line {extra_id} was not found.")
            raise ConflictError(
                f"Supplier order line {extra_id} does not belong to this supplier order."
            )
        raise ConflictError(
            "Reconciliation must include every supplier order line exactly once."
        )

    allocations = list(
        db.scalars(
            select(SupplierOrderAllocation)
            .where(SupplierOrderAllocation.supplier_order_line_id.in_(lines_by_id))
            .order_by(SupplierOrderAllocation.id)
            .with_for_update()
        ).all()
    )
    allocations_by_line: dict[int, list[SupplierOrderAllocation]] = {}
    for allocation in allocations:
        allocations_by_line.setdefault(allocation.supplier_order_line_id, []).append(
            allocation
        )
    locked_preorders = _lock_preorders(
        db, [allocation.preorder_id for allocation in allocations]
    )
    preorders_by_id = {preorder.id: preorder for preorder in locked_preorders}

    planned: list[tuple[SupplierOrderLine, int, list[Preorder], int]] = []
    for item in data.lines:
        line = lines_by_id[item.line_id]
        line_allocs = allocations_by_line.get(line.id, [])
        allocated_preorders = []
        for allocation in line_allocs:
            preorder = preorders_by_id.get(allocation.preorder_id)
            if preorder is None:
                raise ConflictError(
                    f"Preorder {allocation.preorder_id} was not found for this supplier order."
                )
            allocated_preorders.append(preorder)
        allocated_preorders.sort(key=lambda preorder: (preorder.created_at, preorder.id))
        allocated_ids = {preorder.id for preorder in allocated_preorders}

        if item.arrived_preorder_ids is None:
            selected = _fifo_complete_preorders(
                allocated_preorders, item.received_quantity
            )
        else:
            selected = []
            for preorder_id in item.arrived_preorder_ids:
                if preorder_id not in allocated_ids:
                    missing = db.get(Preorder, preorder_id)
                    if missing is None:
                        raise NotFoundError(f"Preorder {preorder_id} was not found.")
                    raise ConflictError(
                        f"Preorder {preorder_id} is not allocated to supplier order line {line.id}."
                    )
                preorder = preorders_by_id[preorder_id]
                if preorder.status != "ORDERED_FROM_SUPPLIER":
                    raise ConflictError(
                        f"Preorder {preorder.id} must be ORDERED_FROM_SUPPLIER to mark as arrived."
                    )
                selected.append(preorder)
            assigned = sum(preorder.quantity for preorder in selected)
            if assigned > item.received_quantity:
                raise ConflictError(
                    "Selected preorder quantities exceed received_quantity."
                )

        for preorder in selected:
            if preorder.status != "ORDERED_FROM_SUPPLIER":
                raise ConflictError(
                    f"Preorder {preorder.id} must be ORDERED_FROM_SUPPLIER to mark as arrived."
                )
        assigned_quantity = sum(preorder.quantity for preorder in selected)
        remainder = item.received_quantity - assigned_quantity
        planned.append((line, item.received_quantity, selected, remainder))

    try:
        for line, received_quantity, selected, remainder in planned:
            line.received_quantity = received_quantity
            for preorder in selected:
                preorder.status = "ARRIVED"
            if remainder > 0:
                db.add(
                    InventoryLot(
                        product_id=line.product_id,
                        quantity_on_hand=remainder,
                        supplier_order_line_id=line.id,
                    )
                )
        order.status = "RECONCILED"
        order.reconciled_at = utc_now()
        order.reconciliation_notes = data.reconciliation_notes
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_inventory_lot_integrity_error(exc)
        raise
    return _get_supplier_order_loaded(db, order.id)


def list_inventory_lots(
    db: Session, product_id: int | None = None
) -> list[InventoryLot]:
    statement = select(InventoryLot).order_by(InventoryLot.id)
    if product_id is not None:
        statement = statement.where(InventoryLot.product_id == product_id)
    return list(db.scalars(statement).all())


def get_inventory_lot(db: Session, inventory_lot_id: int) -> InventoryLot:
    lot = db.get(InventoryLot, inventory_lot_id)
    if lot is None:
        raise NotFoundError(f"Inventory lot {inventory_lot_id} was not found.")
    return lot


ATTENTION_TYPE_RANK = {
    "preorder_overpaid": 10,
    "supplier_order_needs_reconciliation": 20,
    "preorder_needs_customer_ready": 30,
    "preorder_needs_fulfilment": 40,
    "supplier_order_draft_needs_placement": 50,
    "preorder_needs_supplier_order": 60,
}


def _empty_attention_counts() -> dict[str, int]:
    return {key: 0 for key in ATTENTION_TYPE_RANK}


def list_attention(db: Session) -> AttentionQueue:
    items: list[AttentionItem] = []

    confirmed = (
        select(Preorder, Product.supplier_id)
        .join(Product, Preorder.product_id == Product.id)
        .outerjoin(
            SupplierOrderAllocation,
            SupplierOrderAllocation.preorder_id == Preorder.id,
        )
        .where(Preorder.status == "CONFIRMED")
        .where(SupplierOrderAllocation.id.is_(None))
    )
    for preorder, supplier_id in db.execute(confirmed):
        items.append(
            AttentionItem(
                type="preorder_needs_supplier_order",
                entity_type="preorder",
                entity_id=preorder.id,
                occurred_at=preorder.created_at,
                customer_id=preorder.customer_id,
                product_id=preorder.product_id,
                supplier_id=supplier_id,
            )
        )

    in_hand = (
        select(Preorder, Product.supplier_id)
        .join(Product, Preorder.product_id == Product.id)
        .where(Preorder.status.in_(("ARRIVED", "READY_FOR_CUSTOMER")))
    )
    for preorder, supplier_id in db.execute(in_hand):
        item_type = (
            "preorder_needs_customer_ready"
            if preorder.status == "ARRIVED"
            else "preorder_needs_fulfilment"
        )
        items.append(
            AttentionItem(
                type=item_type,
                entity_type="preorder",
                entity_id=preorder.id,
                occurred_at=preorder.updated_at,
                customer_id=preorder.customer_id,
                product_id=preorder.product_id,
                supplier_id=supplier_id,
            )
        )

    supplier_orders = select(SupplierOrder).where(
        SupplierOrder.status.in_(("DRAFT", "ARRIVED"))
    )
    for order in db.scalars(supplier_orders):
        if order.status == "DRAFT":
            items.append(
                AttentionItem(
                    type="supplier_order_draft_needs_placement",
                    entity_type="supplier_order",
                    entity_id=order.id,
                    occurred_at=order.created_at,
                    supplier_id=order.supplier_id,
                )
            )
        else:
            items.append(
                AttentionItem(
                    type="supplier_order_needs_reconciliation",
                    entity_type="supplier_order",
                    entity_id=order.id,
                    occurred_at=order.updated_at,
                    supplier_id=order.supplier_id,
                )
            )

    overpaid = (
        select(
            Preorder.id,
            Preorder.customer_id,
            Preorder.product_id,
            Product.supplier_id,
            Preorder.quantity,
            Preorder.agreed_price,
            func.sum(Payment.amount),
            func.max(Payment.paid_at),
        )
        .join(Payment, Payment.preorder_id == Preorder.id)
        .join(Product, Preorder.product_id == Product.id)
        .where(Preorder.agreed_price.is_not(None))
        .group_by(
            Preorder.id,
            Preorder.customer_id,
            Preorder.product_id,
            Product.supplier_id,
            Preorder.quantity,
            Preorder.agreed_price,
        )
        .having(func.sum(Payment.amount) > Preorder.quantity * Preorder.agreed_price)
    )
    for (
        preorder_id,
        customer_id,
        product_id,
        supplier_id,
        quantity,
        agreed_price,
        amount_paid,
        paid_at,
    ) in db.execute(overpaid):
        total = Decimal(quantity) * Decimal(agreed_price)
        items.append(
            AttentionItem(
                type="preorder_overpaid",
                entity_type="preorder",
                entity_id=preorder_id,
                occurred_at=paid_at,
                customer_id=customer_id,
                product_id=product_id,
                supplier_id=supplier_id,
                outstanding_balance=total - Decimal(amount_paid),
            )
        )

    items.sort(
        key=lambda item: (
            ATTENTION_TYPE_RANK[item.type],
            item.occurred_at,
            item.entity_type,
            item.entity_id,
        )
    )
    counts = _empty_attention_counts()
    for item in items:
        counts[item.type] += 1
    return AttentionQueue(items=items, counts=AttentionCounts(**counts))


def _as_int(value: object) -> int:
    if value is None:
        return 0
    return int(value)


def _conversion_rate(converted: int, lost: int) -> Decimal | None:
    resolved = converted + lost
    if resolved == 0:
        return None
    return Decimal(converted) / Decimal(resolved)


def _demand_enquiry_filters(from_: datetime | None, to: datetime | None):
    if from_ is not None and to is not None and from_ >= to:
        raise ValueError("from must be earlier than to.")
    filters = []
    if from_ is not None:
        filters.append(Enquiry.enquired_at >= from_)
    if to is not None:
        filters.append(Enquiry.enquired_at < to)
    return filters


def _demand_enquiry_select(*columns, filters: list):
    statement = (
        select(*columns)
        .select_from(Enquiry)
        .join(Product, Product.id == Enquiry.product_id)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .outerjoin(Preorder, Preorder.enquiry_id == Enquiry.id)
    )
    if filters:
        statement = statement.where(*filters)
    return statement


def _is_converted():
    return Preorder.id.is_not(None)


def _is_lost():
    return and_(Preorder.id.is_(None), Enquiry.outcome.in_(LOST_DEMAND_REASONS))


def _is_open():
    return and_(Preorder.id.is_(None), Enquiry.outcome.is_(None))


def _is_unlinked_preordered():
    return and_(Preorder.id.is_(None), Enquiry.outcome == "PREORDERED")


def _is_outcome_mismatch():
    return and_(Preorder.id.is_not(None), Enquiry.outcome.is_distinct_from("PREORDERED"))


def _lost_reason(reason: str):
    return and_(Preorder.id.is_(None), Enquiry.outcome == reason)


def _count_if(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def list_demand_analytics(
    db: Session,
    from_: datetime | None = None,
    to: datetime | None = None,
) -> DemandAnalytics:
    window = _demand_enquiry_filters(from_, to)
    lost_reason_columns = [
        _count_if(_lost_reason(reason)).label(reason) for reason in LOST_DEMAND_REASONS
    ]
    overview_row = db.execute(
        _demand_enquiry_select(
            func.count(Enquiry.id).label("total_enquiries"),
            _count_if(_is_open()).label("open_enquiries"),
            _count_if(_is_converted()).label("converted_enquiries"),
            _count_if(_is_lost()).label("lost_enquiries"),
            func.coalesce(func.sum(Enquiry.quantity), 0).label("requested_quantity"),
            _count_if(_is_unlinked_preordered()).label("unlinked_preordered_outcomes"),
            _count_if(_is_outcome_mismatch()).label("linked_preorder_outcome_mismatch"),
            *lost_reason_columns,
            filters=window,
        )
    ).one()

    converted = _as_int(overview_row.converted_enquiries)
    lost = _as_int(overview_row.lost_enquiries)
    overview = DemandOverview(
        total_enquiries=_as_int(overview_row.total_enquiries),
        open_enquiries=_as_int(overview_row.open_enquiries),
        resolved_enquiries=converted + lost,
        converted_enquiries=converted,
        lost_enquiries=lost,
        requested_quantity=_as_int(overview_row.requested_quantity),
        conversion_rate=_conversion_rate(converted, lost),
        unlinked_preordered_outcomes=_as_int(overview_row.unlinked_preordered_outcomes),
        linked_preorder_outcome_mismatch=_as_int(
            overview_row.linked_preorder_outcome_mismatch
        ),
    )
    lost_demand = [
        LostDemandBucket(reason=reason, count=_as_int(getattr(overview_row, reason)))
        for reason in LOST_DEMAND_REASONS
    ]

    product_rows = db.execute(
        _demand_enquiry_select(
            Product.id.label("product_id"),
            Product.name,
            Product.style,
            Product.colour,
            Product.size,
            Product.supplier_id,
            Supplier.name.label("supplier_name"),
            func.count(Enquiry.id).label("enquiry_count"),
            func.count(func.distinct(Enquiry.customer_id)).label("distinct_customers"),
            func.coalesce(func.sum(Enquiry.quantity), 0).label("requested_quantity"),
            _count_if(_is_converted()).label("converted_enquiries"),
            _count_if(_is_lost()).label("lost_enquiries"),
            _count_if(_is_open()).label("open_enquiries"),
            filters=window,
        )
        .group_by(
            Product.id,
            Product.name,
            Product.style,
            Product.colour,
            Product.size,
            Product.supplier_id,
            Supplier.name,
        )
        .order_by(
            func.count(Enquiry.id).desc(),
            func.coalesce(func.sum(Enquiry.quantity), 0).desc(),
            Product.id.asc(),
        )
    ).all()
    products = [
        ProductDemandRow(
            product_id=row.product_id,
            name=row.name,
            style=row.style,
            colour=row.colour,
            size=row.size,
            supplier_id=row.supplier_id,
            supplier_name=row.supplier_name,
            enquiry_count=_as_int(row.enquiry_count),
            distinct_customers=_as_int(row.distinct_customers),
            requested_quantity=_as_int(row.requested_quantity),
            converted_enquiries=_as_int(row.converted_enquiries),
            lost_enquiries=_as_int(row.lost_enquiries),
            open_enquiries=_as_int(row.open_enquiries),
            conversion_rate=_conversion_rate(
                _as_int(row.converted_enquiries), _as_int(row.lost_enquiries)
            ),
        )
        for row in product_rows
    ]

    supplier_rows = db.execute(
        _demand_enquiry_select(
            Supplier.id.label("supplier_id"),
            Supplier.name,
            func.count(Enquiry.id).label("enquiry_count"),
            func.count(func.distinct(Enquiry.customer_id)).label("distinct_customers"),
            func.coalesce(func.sum(Enquiry.quantity), 0).label("requested_quantity"),
            _count_if(_is_converted()).label("converted_enquiries"),
            _count_if(_is_lost()).label("lost_enquiries"),
            _count_if(_is_open()).label("open_enquiries"),
            filters=window,
        )
        .group_by(Supplier.id, Supplier.name)
        .order_by(func.count(Enquiry.id).desc(), Supplier.id.asc())
    ).all()
    suppliers = [
        SupplierDemandRow(
            supplier_id=row.supplier_id,
            name=row.name,
            enquiry_count=_as_int(row.enquiry_count),
            distinct_customers=_as_int(row.distinct_customers),
            requested_quantity=_as_int(row.requested_quantity),
            converted_enquiries=_as_int(row.converted_enquiries),
            lost_enquiries=_as_int(row.lost_enquiries),
            open_enquiries=_as_int(row.open_enquiries),
            conversion_rate=_conversion_rate(
                _as_int(row.converted_enquiries), _as_int(row.lost_enquiries)
            ),
        )
        for row in supplier_rows
    ]

    ordered = SupplierOrderLine.quantity
    received = func.coalesce(SupplierOrderLine.received_quantity, 0)
    fulfilment_row = db.execute(
        select(
            func.count(func.distinct(SupplierOrder.id)).label("reconciled_order_count"),
            func.coalesce(func.sum(ordered), 0).label("ordered_quantity"),
            func.coalesce(func.sum(received), 0).label("received_quantity"),
            func.coalesce(func.sum(func.greatest(0, ordered - received)), 0).label(
                "shortage_units"
            ),
            func.coalesce(func.sum(func.greatest(0, received - ordered)), 0).label(
                "excess_units"
            ),
        )
        .select_from(SupplierOrder)
        .join(SupplierOrderLine, SupplierOrderLine.supplier_order_id == SupplierOrder.id)
        .where(SupplierOrder.status == "RECONCILED")
    ).one()
    fulfilment = FulfilmentSnapshot(
        date_basis="all_time",
        reconciled_order_count=_as_int(fulfilment_row.reconciled_order_count),
        ordered_quantity=_as_int(fulfilment_row.ordered_quantity),
        received_quantity=_as_int(fulfilment_row.received_quantity),
        shortage_units=_as_int(fulfilment_row.shortage_units),
        excess_units=_as_int(fulfilment_row.excess_units),
    )

    return DemandAnalytics(
        from_=from_,
        to=to,
        overview=overview,
        lost_demand=lost_demand,
        products=products,
        suppliers=suppliers,
        fulfilment=fulfilment,
    )
