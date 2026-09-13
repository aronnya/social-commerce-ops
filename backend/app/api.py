from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import services
from app.core.db import get_db
from app.schemas import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)

router = APIRouter()


def _http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, services.NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, services.ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("/suppliers", response_model=list[SupplierRead])
def list_suppliers(db: Session = Depends(get_db)) -> list[SupplierRead]:
    return services.list_suppliers(db)


@router.post("/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)) -> SupplierRead:
    return services.create_supplier(db, payload)


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)) -> SupplierRead:
    try:
        return services.get_supplier(db, supplier_id)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)
) -> SupplierRead:
    try:
        return services.update_supplier(db, supplier_id, payload)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)) -> None:
    try:
        services.delete_supplier(db, supplier_id)
    except (services.NotFoundError, services.ConflictError) as exc:
        _http_error(exc)


@router.get("/products", response_model=list[ProductRead])
def list_products(
    supplier_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ProductRead]:
    return services.list_products(db, supplier_id=supplier_id)


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> ProductRead:
    try:
        return services.create_product(db, payload)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductRead:
    try:
        return services.get_product(db, product_id)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)
) -> ProductRead:
    try:
        return services.update_product(db, product_id, payload)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    try:
        services.delete_product(db, product_id)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.get("/customers", response_model=list[CustomerRead])
def list_customers(db: Session = Depends(get_db)) -> list[CustomerRead]:
    return services.list_customers(db)


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> CustomerRead:
    return services.create_customer(db, payload)


@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerRead:
    try:
        return services.get_customer(db, customer_id)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.patch("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)
) -> CustomerRead:
    try:
        return services.update_customer(db, customer_id, payload)
    except services.NotFoundError as exc:
        _http_error(exc)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> None:
    try:
        services.delete_customer(db, customer_id)
    except services.NotFoundError as exc:
        _http_error(exc)
