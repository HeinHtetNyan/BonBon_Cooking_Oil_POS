"""Add price_per_viss to voucher_items.

Revision ID: 006
Revises: 005
Create Date: 2026-05-12

Changes:
  - voucher_items: add price_per_viss NUMERIC(18,4) NOT NULL DEFAULT 0
  - Backfill existing rows:
      VISS unit  → price_per_viss = unit_price
      TICAL unit → price_per_viss = unit_price * 100
      (other units default to 0 — none expected in production)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column as nullable first so we can backfill before applying NOT NULL
    op.add_column(
        "voucher_items",
        sa.Column("price_per_viss", sa.Numeric(18, 4), nullable=True),
    )

    # Backfill: derive price_per_viss from existing unit_price + unit
    op.execute(
        """
        UPDATE voucher_items
        SET price_per_viss = CASE
            WHEN unit = 'viss'  THEN unit_price
            WHEN unit = 'tical' THEN unit_price * 100
            ELSE 0
        END
        """
    )

    # Now enforce NOT NULL with a safe default of 0 for any unhandled rows
    op.execute(
        "UPDATE voucher_items SET price_per_viss = 0 WHERE price_per_viss IS NULL"
    )
    op.alter_column("voucher_items", "price_per_viss", nullable=False)


def downgrade() -> None:
    op.drop_column("voucher_items", "price_per_viss")
