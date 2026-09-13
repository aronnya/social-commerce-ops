from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Enquiry, Preorder, Product, Supplier
from app.schemas import (
    CustomerCreate,
    CustomerUpdate,
    EnquiryCreate,
    EnquiryUpdate,
    PreorderCreate,
    PreorderTransition,
    PreorderUpdate,
    ProductCreate,
    ProductUpdate,
    SupplierCreate,
    SupplierUpdate,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


# Isolated allow-list so SupplierOrder can later own ORDERED_FROM_SUPPLIER.
PREORDER_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CONFIRMED": frozenset({"ORDERED_FROM_SUPPLIER", "CANCELLED", "SUPPLIER_UNAVAILABLE"}),
    "ORDERED_FROM_SUPPLIER": frozenset({"ARRIVED", "CANCELLED", "SUPPLIER_UNAVAILABLE"}),
    "ARRIVED": frozenset({"READY_FOR_CUSTOMER", "SUPPLIER_UNAVAILABLE"}),
    "READY_FOR_CUSTOMER": frozenset({"FULFILLED", "CANCELLED"}),
    "FULFILLED": frozenset(),
    "CANCELLED": frozenset(),
    "SUPPLIER_UNAVAILABLE": frozenset(),
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
    if preorder.status != "CONFIRMED" and (
        "quantity" in updates or "agreed_price" in updates
    ):
        raise ConflictError(
            "Quantity and agreed price can only be changed while the preorder is CONFIRMED."
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
