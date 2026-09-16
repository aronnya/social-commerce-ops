"""Add reconciliation fields and inventory lots.

Revision ID: 0006_reconciliation_inventory
Revises: 0005_supplier_orders
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_reconciliation_inventory"
down_revision = "0005_supplier_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_order_lines",
        sa.Column("received_quantity", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_supplier_order_lines_received_quantity_non_negative",
        "supplier_order_lines",
        "received_quantity IS NULL OR received_quantity >= 0",
    )
    op.add_column(
        "supplier_orders",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "supplier_orders",
        sa.Column("reconciliation_notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("supplier_order_line_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["supplier_order_line_id"], ["supplier_order_lines.id"]),
        sa.CheckConstraint(
            "quantity_on_hand >= 0",
            name="ck_inventory_lots_quantity_on_hand_non_negative",
        ),
    )
    op.create_index("ix_inventory_lots_product_id", "inventory_lots", ["product_id"])
    op.create_index(
        "ix_inventory_lots_supplier_order_line_id",
        "inventory_lots",
        ["supplier_order_line_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_lots_supplier_order_line_id", table_name="inventory_lots"
    )
    op.drop_index("ix_inventory_lots_product_id", table_name="inventory_lots")
    op.drop_table("inventory_lots")
    op.drop_column("supplier_orders", "reconciliation_notes")
    op.drop_column("supplier_orders", "reconciled_at")
    op.drop_constraint(
        "ck_supplier_order_lines_received_quantity_non_negative",
        "supplier_order_lines",
        type_="check",
    )
    op.drop_column("supplier_order_lines", "received_quantity")
