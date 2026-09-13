"""Create supplier orders, lines, and allocations.

Revision ID: 0005_supplier_orders
Revises: 0004_payments
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_supplier_orders"
down_revision = "0004_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.CheckConstraint(
            "status IN ("
            "'DRAFT', 'PLACED', 'CONFIRMED', 'DISPATCHED', 'ARRIVED', 'RECONCILED'"
            ")",
            name="ck_supplier_orders_status",
        ),
    )
    op.create_index("ix_supplier_orders_supplier_id", "supplier_orders", ["supplier_id"])
    op.create_index("ix_supplier_orders_status", "supplier_orders", ["status"])

    op.create_table(
        "supplier_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supplier_order_id"], ["supplier_orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.CheckConstraint(
            "quantity >= 1", name="ck_supplier_order_lines_quantity_positive"
        ),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_supplier_order_lines_unit_cost_non_negative",
        ),
        sa.UniqueConstraint(
            "supplier_order_id",
            "product_id",
            name="uq_supplier_order_lines_order_product",
        ),
    )
    op.create_index(
        "ix_supplier_order_lines_supplier_order_id",
        "supplier_order_lines",
        ["supplier_order_id"],
    )
    op.create_index(
        "ix_supplier_order_lines_product_id", "supplier_order_lines", ["product_id"]
    )

    op.create_table(
        "supplier_order_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_order_line_id", sa.Integer(), nullable=False),
        sa.Column("preorder_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_order_line_id"], ["supplier_order_lines.id"]),
        sa.ForeignKeyConstraint(["preorder_id"], ["preorders.id"]),
        sa.CheckConstraint(
            "quantity >= 1", name="ck_supplier_order_allocations_quantity_positive"
        ),
    )
    op.create_index(
        "ix_supplier_order_allocations_supplier_order_line_id",
        "supplier_order_allocations",
        ["supplier_order_line_id"],
    )
    op.create_index(
        "ix_supplier_order_allocations_preorder_id",
        "supplier_order_allocations",
        ["preorder_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_supplier_order_allocations_preorder_id",
        table_name="supplier_order_allocations",
    )
    op.drop_index(
        "ix_supplier_order_allocations_supplier_order_line_id",
        table_name="supplier_order_allocations",
    )
    op.drop_table("supplier_order_allocations")

    op.drop_index(
        "ix_supplier_order_lines_product_id", table_name="supplier_order_lines"
    )
    op.drop_index(
        "ix_supplier_order_lines_supplier_order_id",
        table_name="supplier_order_lines",
    )
    op.drop_table("supplier_order_lines")

    op.drop_index("ix_supplier_orders_status", table_name="supplier_orders")
    op.drop_index("ix_supplier_orders_supplier_id", table_name="supplier_orders")
    op.drop_table("supplier_orders")
