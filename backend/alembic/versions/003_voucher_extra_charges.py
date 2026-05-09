"""Add extra_charges column to vouchers.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vouchers",
        sa.Column("extra_charges", sa.Text(), nullable=True, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("vouchers", "extra_charges")
