"""Create preorders.

Revision ID: 0003_preorders
Revises: 0002_enquiries
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_preorders"
down_revision = "0002_enquiries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preorders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("enquiry_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONFIRMED"),
        sa.Column("agreed_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["enquiry_id"], ["enquiries.id"]),
        sa.CheckConstraint("quantity >= 1", name="ck_preorders_quantity_positive"),
        sa.CheckConstraint(
            "agreed_price IS NULL OR agreed_price >= 0",
            name="ck_preorders_agreed_price_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'CONFIRMED', 'ORDERED_FROM_SUPPLIER', 'ARRIVED', "
            "'READY_FOR_CUSTOMER', 'FULFILLED', 'CANCELLED', "
            "'SUPPLIER_UNAVAILABLE'"
            ")",
            name="ck_preorders_status",
        ),
    )
    op.create_index("ix_preorders_customer_id", "preorders", ["customer_id"])
    op.create_index("ix_preorders_product_id", "preorders", ["product_id"])
    op.create_index("ix_preorders_status", "preorders", ["status"])
    op.create_index("ix_preorders_enquiry_id", "preorders", ["enquiry_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_preorders_enquiry_id", table_name="preorders")
    op.drop_index("ix_preorders_status", table_name="preorders")
    op.drop_index("ix_preorders_product_id", table_name="preorders")
    op.drop_index("ix_preorders_customer_id", table_name="preorders")
    op.drop_table("preorders")
