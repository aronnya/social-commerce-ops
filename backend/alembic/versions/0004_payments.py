"""Create payments.

Revision ID: 0004_payments
Revises: 0003_preorders
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_payments"
down_revision = "0003_preorders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preorder_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["preorder_id"], ["preorders.id"]),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "method IN ('BANK_TRANSFER', 'REVOLUT')",
            name="ck_payments_method",
        ),
    )
    op.create_index("ix_payments_preorder_id", "payments", ["preorder_id"])
    op.create_index("ix_payments_paid_at", "payments", ["paid_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_paid_at", table_name="payments")
    op.drop_index("ix_payments_preorder_id", table_name="payments")
    op.drop_table("payments")
