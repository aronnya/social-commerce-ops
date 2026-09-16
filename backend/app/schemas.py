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


PaymentMethod = Literal["BANK_TRANSFER", "REVOLUT"]

PaymentSummaryStatus = Literal["UNPAID", "PARTIALLY_PAID", "PAID", "OVERPAID"]


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


class PaymentSummary(BaseModel):
    total_amount: Decimal | None
    amount_paid: Decimal
    outstanding_balance: Decimal | None
    status: PaymentSummaryStatus | None


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
    payment_summary: PaymentSummary


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0)
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=200)
    paid_at: AwareDatetime | None = None
    notes: str | None = None

    @field_validator("reference", "notes", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        return _strip_optional_text(value)


class PaymentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("reference", "notes", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        return _strip_optional_text(value)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    preorder_id: int
    amount: Decimal
    method: PaymentMethod
    reference: str | None
    paid_at: datetime
    notes: str | None
    created_at: datetime
    updated_at: datetime


SupplierOrderStatus = Literal[
    "DRAFT",
    "PLACED",
    "CONFIRMED",
    "DISPATCHED",
    "ARRIVED",
    "RECONCILED",
]

SupplierOrderTransitionStatus = Literal[
    "CONFIRMED",
    "DISPATCHED",
    "ARRIVED",
]


class SupplierOrderAllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    preorder_id: int
    quantity: int = Field(ge=1)


class SupplierOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int = Field(ge=1)
    received_quantity: int | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None
    allocations: list[SupplierOrderAllocationRead]


class SupplierOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    status: SupplierOrderStatus
    notes: str | None
    placed_at: datetime | None
    reconciled_at: datetime | None = None
    reconciliation_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    lines: list[SupplierOrderLineRead]


class SupplierOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: object) -> object:
        return _strip_optional_text(value)


class SupplierOrderGenerateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: int
    preorder_ids: list[int] | None = Field(default=None, min_length=1)

    @field_validator("preorder_ids")
    @classmethod
    def reject_duplicate_preorder_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("preorder_ids must not contain duplicates.")
        return value


class SupplierOrderTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SupplierOrderTransitionStatus


class ReconciliationLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: int
    received_quantity: int = Field(ge=0)
    arrived_preorder_ids: list[int] | None = None

    @field_validator("arrived_preorder_ids")
    @classmethod
    def reject_duplicate_arrived_preorder_ids(
        cls, value: list[int] | None
    ) -> list[int] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("arrived_preorder_ids must not contain duplicates.")
        return value


class SupplierOrderReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[ReconciliationLineInput] = Field(min_length=1)
    reconciliation_notes: str | None = None

    @field_validator("reconciliation_notes", mode="before")
    @classmethod
    def strip_notes(cls, value: object) -> object:
        return _strip_optional_text(value)

    @field_validator("lines")
    @classmethod
    def reject_duplicate_line_ids(
        cls, value: list[ReconciliationLineInput]
    ) -> list[ReconciliationLineInput]:
        line_ids = [item.line_id for item in value]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("lines must not contain duplicate line_id values.")
        return value


class InventoryLotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity_on_hand: int = Field(ge=0)
    supplier_order_line_id: int | None
    created_at: datetime
    updated_at: datetime


AttentionType = Literal[
    "preorder_overpaid",
    "supplier_order_needs_reconciliation",
    "preorder_needs_customer_ready",
    "preorder_needs_fulfilment",
    "supplier_order_draft_needs_placement",
    "preorder_needs_supplier_order",
]

AttentionEntityType = Literal["preorder", "supplier_order"]


class AttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AttentionType
    entity_type: AttentionEntityType
    entity_id: int
    occurred_at: datetime
    customer_id: int | None = None
    product_id: int | None = None
    supplier_id: int | None = None
    outstanding_balance: Decimal | None = None


class AttentionCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preorder_overpaid: int = 0
    supplier_order_needs_reconciliation: int = 0
    preorder_needs_customer_ready: int = 0
    preorder_needs_fulfilment: int = 0
    supplier_order_draft_needs_placement: int = 0
    preorder_needs_supplier_order: int = 0


class AttentionQueue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AttentionItem]
    counts: AttentionCounts
