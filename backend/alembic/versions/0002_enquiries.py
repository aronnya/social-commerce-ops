"""Create enquiries.

Revision ID: 0002_enquiries
Revises: 0001_catalogue_core
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_enquiries"
down_revision = "0001_catalogue_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enquiries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("enquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.CheckConstraint("quantity >= 1", name="ck_enquiries_quantity_positive"),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ("
            "'PREORDERED', 'TOO_EXPENSIVE', 'SUPPLIER_UNAVAILABLE', "
            "'CUSTOMER_GHOSTED', 'WRONG_SIZE', 'NOT_INTERESTED'"
            ")",
            name="ck_enquiries_outcome",
        ),
    )
    op.create_index("ix_enquiries_customer_id", "enquiries", ["customer_id"])
    op.create_index("ix_enquiries_product_id", "enquiries", ["product_id"])
    op.create_index("ix_enquiries_outcome", "enquiries", ["outcome"])


def downgrade() -> None:
    op.drop_index("ix_enquiries_outcome", table_name="enquiries")
    op.drop_index("ix_enquiries_product_id", table_name="enquiries")
    op.drop_index("ix_enquiries_customer_id", table_name="enquiries")
    op.drop_table("enquiries")
