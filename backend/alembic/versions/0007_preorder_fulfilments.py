"""Add customer fulfilment records.

Revision ID: 0007_preorder_fulfilments
Revises: 0006_reconciliation_inventory

Additive only. Preorders already marked FULFILLED are not backfilled;
they may have no fulfilment row because they predate this table.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_preorder_fulfilments"
down_revision = "0006_reconciliation_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fulfilments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preorder_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("postage_type", sa.String(length=32), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("postage_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("tracking_reference", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["preorder_id"], ["preorders.id"]),
        sa.UniqueConstraint("preorder_id", name="uq_fulfilments_preorder_id"),
        sa.CheckConstraint(
            "method IN ('HOME_COLLECTION', 'POST')",
            name="ck_fulfilments_method",
        ),
        sa.CheckConstraint(
            "postage_type IS NULL OR postage_type IN ('REGULAR', 'REGISTERED')",
            name="ck_fulfilments_postage_type",
        ),
        sa.CheckConstraint(
            "postage_cost IS NULL OR postage_cost >= 0",
            name="ck_fulfilments_postage_cost_non_negative",
        ),
        sa.CheckConstraint(
            "("
            "method = 'HOME_COLLECTION'"
            " AND postage_type IS NULL"
            " AND delivery_address IS NULL"
            " AND postage_cost IS NULL"
            " AND tracking_reference IS NULL"
            ") OR ("
            "method = 'POST'"
            " AND postage_type = 'REGULAR'"
            " AND delivery_address IS NOT NULL"
            " AND btrim(delivery_address) <> ''"
            " AND tracking_reference IS NULL"
            ") OR ("
            "method = 'POST'"
            " AND postage_type = 'REGISTERED'"
            " AND delivery_address IS NOT NULL"
            " AND btrim(delivery_address) <> ''"
            " AND tracking_reference IS NOT NULL"
            " AND btrim(tracking_reference) <> ''"
            ")",
            name="ck_fulfilments_method_fields",
        ),
    )


def downgrade() -> None:
    op.drop_table("fulfilments")
