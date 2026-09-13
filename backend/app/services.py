from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Product, Supplier
from app.schemas import (
    CustomerCreate,
    CustomerUpdate,
    ProductCreate,
    ProductUpdate,
    SupplierCreate,
    SupplierUpdate,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


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
    db.delete(customer)
    db.commit()
