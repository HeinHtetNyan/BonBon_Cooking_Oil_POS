"""Add transaction_date to movements, purchase_date to items.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09

Changes:
  - inventory_movements: add transaction_date (String 10, nullable) for custom purchase/entry dates
  - inventory_items:     add purchase_date   (String 10, nullable) for tracking item acquisition date
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_movements",
        sa.Column("transaction_date", sa.String(10), nullable=True),
    )
    op.add_column(
        "inventory_items",
        sa.Column("purchase_date", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inventory_movements", "transaction_date")
    op.drop_column("inventory_items", "purchase_date")
