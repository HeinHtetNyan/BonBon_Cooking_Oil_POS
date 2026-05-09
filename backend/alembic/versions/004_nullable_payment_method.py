"""Make voucher_payments.payment_method_id nullable.

Revision ID: 004_nullable_payment_method
Revises: 003_voucher_extra_charges
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "voucher_payments",
        "payment_method_id",
        nullable=True,
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
    )


def downgrade() -> None:
    # Set a placeholder before making non-nullable again would require a default
    # Just mark as nullable=False – may fail if NULL rows exist
    op.alter_column(
        "voucher_payments",
        "payment_method_id",
        nullable=False,
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
    )
