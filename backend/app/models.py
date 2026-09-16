from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


ENQUIRY_OUTCOMES = (
    "PREORDERED",
    "TOO_EXPENSIVE",
    "SUPPLIER_UNAVAILABLE",
    "CUSTOMER_GHOSTED",
    "WRONG_SIZE",
    "NOT_INTERESTED",
)


PREORDER_STATUSES = (
    "CONFIRMED",
    "ORDERED_FROM_SUPPLIER",
    "ARRIVED",
    "READY_FOR_CUSTOMER",
    "FULFILLED",
    "CANCELLED",
    "SUPPLIER_UNAVAILABLE",
)


PAYMENT_METHODS = (
    "BANK_TRANSFER",
    "REVOLUT",
)


SUPPLIER_ORDER_STATUSES = (
    "DRAFT",
    "PLACED",
    "CONFIRMED",
    "DISPATCHED",
    "ARRIVED",
    "RECONCILED",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    products: Mapped[list["Product"]] = relationship(back_populates="supplier")
    orders: Mapped[list["SupplierOrder"]] = relationship(back_populates="supplier")


class Product(Base):
    """Catalogue item from a supplier. This is not physical inventory."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    supplier_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    supplier: Mapped[Supplier] = relationship(back_populates="products")
    enquiries: Mapped[list["Enquiry"]] = relationship(back_populates="product")
    preorders: Mapped[list["Preorder"]] = relationship(back_populates="product")
    supplier_order_lines: Mapped[list["SupplierOrderLine"]] = relationship(
        back_populates="product"
    )
    inventory_lots: Mapped[list["InventoryLot"]] = relationship(back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    facebook_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    enquiries: Mapped[list["Enquiry"]] = relationship(back_populates="customer")
    preorders: Mapped[list["Preorder"]] = relationship(back_populates="customer")


class Enquiry(Base):
    """Customer interest in a catalogue product. This is not a preorder."""

    __tablename__ = "enquiries"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_enquiries_quantity_positive"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ("
            + ", ".join(f"'{value}'" for value in ENQUIRY_OUTCOMES)
            + ")",
            name="ck_enquiries_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    enquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    customer: Mapped[Customer] = relationship(back_populates="enquiries")
    product: Mapped[Product] = relationship(back_populates="enquiries")
    preorder: Mapped["Preorder | None"] = relationship(
        back_populates="enquiry", uselist=False
    )


class Preorder(Base):
    """Customer commitment to buy a catalogue product. This is not an enquiry."""

    __tablename__ = "preorders"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_preorders_quantity_positive"),
        CheckConstraint(
            "agreed_price IS NULL OR agreed_price >= 0",
            name="ck_preorders_agreed_price_non_negative",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in PREORDER_STATUSES) + ")",
            name="ck_preorders_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    enquiry_id: Mapped[int | None] = mapped_column(
        ForeignKey("enquiries.id"), nullable=True, unique=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="CONFIRMED", index=True)
    agreed_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    customer: Mapped[Customer] = relationship(back_populates="preorders")
    product: Mapped[Product] = relationship(back_populates="preorders")
    enquiry: Mapped[Enquiry | None] = relationship(back_populates="preorder")
    payments: Mapped[list["Payment"]] = relationship(back_populates="preorder")
    supplier_order_allocation: Mapped["SupplierOrderAllocation | None"] = relationship(
        back_populates="preorder", uselist=False
    )


class Payment(Base):
    """Money received against a preorder. Status is derived, not stored."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "method IN (" + ", ".join(f"'{value}'" for value in PAYMENT_METHODS) + ")",
            name="ck_payments_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preorder_id: Mapped[int] = mapped_column(ForeignKey("preorders.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(32))
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    preorder: Mapped[Preorder] = relationship(back_populates="payments")


class SupplierOrder(Base):
    """A batch of demand sent to one supplier. Status is separate from Preorder."""

    __tablename__ = "supplier_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{value}'" for value in SUPPLIER_ORDER_STATUSES)
            + ")",
            name="ck_supplier_orders_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciliation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    supplier: Mapped[Supplier] = relationship(back_populates="orders")
    lines: Mapped[list["SupplierOrderLine"]] = relationship(back_populates="supplier_order")


class SupplierOrderLine(Base):
    """Consolidated product row on a supplier order."""

    __tablename__ = "supplier_order_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_supplier_order_lines_quantity_positive"),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_supplier_order_lines_unit_cost_non_negative",
        ),
        CheckConstraint(
            "received_quantity IS NULL OR received_quantity >= 0",
            name="ck_supplier_order_lines_received_quantity_non_negative",
        ),
        UniqueConstraint(
            "supplier_order_id",
            "product_id",
            name="uq_supplier_order_lines_order_product",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_order_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_orders.id"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    received_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    supplier_order: Mapped[SupplierOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(back_populates="supplier_order_lines")
    allocations: Mapped[list["SupplierOrderAllocation"]] = relationship(
        back_populates="line"
    )
    inventory_lot: Mapped["InventoryLot | None"] = relationship(
        back_populates="supplier_order_line", uselist=False
    )


class SupplierOrderAllocation(Base):
    """Links one preorder to the supplier-order line that covers it."""

    __tablename__ = "supplier_order_allocations"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1", name="ck_supplier_order_allocations_quantity_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_order_line_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_order_lines.id"), index=True
    )
    preorder_id: Mapped[int] = mapped_column(
        ForeignKey("preorders.id"), unique=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)

    line: Mapped[SupplierOrderLine] = relationship(back_populates="allocations")
    preorder: Mapped[Preorder] = relationship(back_populates="supplier_order_allocation")


class InventoryLot(Base):
    """Physically owned stock not bound to a customer preorder."""

    __tablename__ = "inventory_lots"
    __table_args__ = (
        CheckConstraint(
            "quantity_on_hand >= 0", name="ck_inventory_lots_quantity_on_hand_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer)
    supplier_order_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_order_lines.id"), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    product: Mapped[Product] = relationship(back_populates="inventory_lots")
    supplier_order_line: Mapped[SupplierOrderLine | None] = relationship(
        back_populates="inventory_lot"
    )
