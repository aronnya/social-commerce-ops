from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


def _strip_supplier_name(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


def _strip_optional_text(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


EnquiryOutcome = Literal[
    "PREORDERED",
    "TOO_EXPENSIVE",
    "SUPPLIER_UNAVAILABLE",
    "CUSTOMER_GHOSTED",
    "WRONG_SIZE",
    "NOT_INTERESTED",
]


PreorderStatus = Literal[
    "CONFIRMED",
    "ORDERED_FROM_SUPPLIER",
    "ARRIVED",
    "READY_FOR_CUSTOMER",
    "FULFILLED",
    "CANCELLED",
    "SUPPLIER_UNAVAILABLE",
]


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    whatsapp: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_supplier_name(value)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    whatsapp: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_supplier_name(value)


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_name: str | None
    phone: str | None
    whatsapp: str | None
    email: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    supplier_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    style: str | None = Field(default=None, max_length=100)
    colour: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=50)
    supplier_cost: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_supplier_name(value)


class ProductUpdate(BaseModel):
    supplier_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    style: str | None = Field(default=None, max_length=100)
    colour: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=50)
    supplier_cost: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_supplier_name(value)


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    name: str
    description: str | None
    style: str | None
    colour: str | None
    size: str | None
    supplier_cost: Decimal | None
    selling_price: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    facebook_name: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_supplier_name(value)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    facebook_name: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_supplier_name(value)


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    facebook_name: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EnquiryCreate(BaseModel):
    customer_id: int
    product_id: int
    quantity: int = Field(default=1, ge=1)
    outcome: EnquiryOutcome | None = None
    notes: str | None = None
    enquired_at: AwareDatetime | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: object) -> object:
        return _strip_optional_text(value)


class EnquiryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = Field(default=None, ge=1)
    outcome: EnquiryOutcome | None = None
    notes: str | None = None
    enquired_at: AwareDatetime | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: object) -> object:
        return _strip_optional_text(value)


class EnquiryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    product_id: int
    quantity: int
    outcome: EnquiryOutcome | None
    notes: str | None
    enquired_at: datetime
    created_at: datetime
    updated_at: datetime


class PreorderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int
    product_id: int
    enquiry_id: int | None = None
    quantity: int = Field(default=1, ge=1)
    agreed_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: object) -> object:
        return _strip_optional_text(value)


class PreorderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = Field(default=None, ge=1)
    agreed_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: object) -> object:
        return _strip_optional_text(value)


class PreorderTransition(BaseModel):
    status: PreorderStatus


class PreorderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    product_id: int
    enquiry_id: int | None
    quantity: int
    status: PreorderStatus
    agreed_price: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
