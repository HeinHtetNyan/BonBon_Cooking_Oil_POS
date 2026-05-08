"""Phase 3 hardening: concurrency safety, offline sync, integrity tables.

Revision ID: 002
Revises: 001
Create Date: 2026-05-09

Changes:
  A. New tables
     - idempotency_keys       : duplicate-request protection
     - financial_snapshots    : daily/monthly financial balance checkpoints
     - change_events          : ordered event log for offline-sync engine

  B. New columns on existing tables
     - version_number (INTEGER, DEFAULT 1) on:
       vouchers, customers, inventory_items, production_batches, expenses
     - sync fields (sync_version, client_generated_id, last_synced_at,
       device_id, sync_status) on:
       vouchers, customers, inventory_movements, expenses, production_batches

  C. Indexes
     All new columns that support filter or sort queries get explicit indexes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A1. idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("key", name="uq_idempotency_keys_key"),
    )
    op.create_index("ix_idempotency_keys_key", "idempotency_keys", ["key"])
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])

    # A2. financial_snapshots
    op.create_table(
        "financial_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(18, 4), nullable=False),
        sa.Column("snapshot_type", sa.String(16), nullable=False, server_default="daily"),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["account_id"], ["financial_accounts.id"],
                                ondelete="RESTRICT",
                                name="fk_financial_snapshots_account_id"),
        sa.UniqueConstraint("account_id", "snapshot_date", "snapshot_type",
                            name="uq_financial_snapshot_account_date_type"),
    )
    op.create_index("ix_financial_snapshots_account_id", "financial_snapshots", ["account_id"])
    op.create_index("ix_financial_snapshots_snapshot_date", "financial_snapshots", ["snapshot_date"])

    # A3. change_events
    op.create_table(
        "change_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("delta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False,
                  autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # Sequence for change_events.sequence_number (monotonic ordering)
    op.execute(
        "CREATE SEQUENCE IF NOT EXISTS change_events_sequence_number_seq "
        "START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1"
    )
    op.execute(
        "ALTER TABLE change_events ALTER COLUMN sequence_number "
        "SET DEFAULT nextval('change_events_sequence_number_seq')"
    )
    op.create_index("ix_change_events_entity", "change_events", ["entity_type", "entity_id"])
    op.create_index("ix_change_events_sequence", "change_events", ["sequence_number"])
    op.create_index("ix_change_events_tenant_sequence", "change_events",
                    ["tenant_id", "sequence_number"])
    op.create_index("ix_change_events_created_at", "change_events", ["created_at"])

    # B. version_number columns
    for table in ("vouchers", "customers", "inventory_items", "production_batches", "expenses"):
        op.add_column(table, sa.Column("version_number", sa.Integer(), nullable=False,
                                       server_default="1"))
        op.create_index(f"ix_{table}_version_number", table, ["version_number"])

    # C. Sync fields on vouchers
    op.add_column("vouchers", sa.Column("sync_version", sa.Integer(), nullable=False,
                                         server_default="0"))
    op.add_column("vouchers", sa.Column("client_generated_id", sa.String(36), nullable=True))
    op.add_column("vouchers", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vouchers", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("vouchers", sa.Column("sync_status", sa.String(16), nullable=False,
                                         server_default="synced"))
    op.create_index("ix_vouchers_client_generated_id", "vouchers", ["client_generated_id"])
    op.create_index("ix_vouchers_sync_status", "vouchers", ["sync_status"])

    # C. Sync fields on customers
    op.add_column("customers", sa.Column("sync_version", sa.Integer(), nullable=False,
                                          server_default="0"))
    op.add_column("customers", sa.Column("client_generated_id", sa.String(36), nullable=True))
    op.add_column("customers", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("customers", sa.Column("sync_status", sa.String(16), nullable=False,
                                          server_default="synced"))
    op.create_index("ix_customers_client_generated_id", "customers", ["client_generated_id"])

    # C. Sync fields on inventory_movements
    op.add_column("inventory_movements", sa.Column("sync_version", sa.Integer(), nullable=False,
                                                    server_default="0"))
    op.add_column("inventory_movements", sa.Column("client_generated_id", sa.String(36), nullable=True))
    op.add_column("inventory_movements", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inventory_movements", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("inventory_movements", sa.Column("sync_status", sa.String(16), nullable=False,
                                                    server_default="synced"))
    op.create_index("ix_inventory_movements_client_generated_id", "inventory_movements",
                    ["client_generated_id"])

    # C. Sync fields on expenses
    op.add_column("expenses", sa.Column("sync_version", sa.Integer(), nullable=False,
                                         server_default="0"))
    op.add_column("expenses", sa.Column("client_generated_id", sa.String(36), nullable=True))
    op.add_column("expenses", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("expenses", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("expenses", sa.Column("sync_status", sa.String(16), nullable=False,
                                         server_default="synced"))
    op.create_index("ix_expenses_client_generated_id", "expenses", ["client_generated_id"])

    # C. Sync fields on production_batches
    op.add_column("production_batches", sa.Column("sync_version", sa.Integer(), nullable=False,
                                                    server_default="0"))
    op.add_column("production_batches", sa.Column("client_generated_id", sa.String(36), nullable=True))
    op.add_column("production_batches", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("production_batches", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("production_batches", sa.Column("sync_status", sa.String(16), nullable=False,
                                                    server_default="synced"))
    op.create_index("ix_production_batches_client_generated_id", "production_batches",
                    ["client_generated_id"])


def downgrade() -> None:
    # Remove sync fields from production_batches
    op.drop_index("ix_production_batches_client_generated_id", "production_batches")
    for col in ("sync_status", "device_id", "last_synced_at", "client_generated_id", "sync_version"):
        op.drop_column("production_batches", col)

    # Remove sync fields from expenses
    op.drop_index("ix_expenses_client_generated_id", "expenses")
    for col in ("sync_status", "device_id", "last_synced_at", "client_generated_id", "sync_version"):
        op.drop_column("expenses", col)

    # Remove sync fields from inventory_movements
    op.drop_index("ix_inventory_movements_client_generated_id", "inventory_movements")
    for col in ("sync_status", "device_id", "last_synced_at", "client_generated_id", "sync_version"):
        op.drop_column("inventory_movements", col)

    # Remove sync fields from customers
    op.drop_index("ix_customers_client_generated_id", "customers")
    for col in ("sync_status", "device_id", "last_synced_at", "client_generated_id", "sync_version"):
        op.drop_column("customers", col)

    # Remove sync fields from vouchers
    op.drop_index("ix_vouchers_sync_status", "vouchers")
    op.drop_index("ix_vouchers_client_generated_id", "vouchers")
    for col in ("sync_status", "device_id", "last_synced_at", "client_generated_id", "sync_version"):
        op.drop_column("vouchers", col)

    # Remove version_number columns
    for table in ("vouchers", "customers", "inventory_items", "production_batches", "expenses"):
        op.drop_index(f"ix_{table}_version_number", table)
        op.drop_column(table, "version_number")

    # Drop new tables
    op.drop_table("change_events")
    op.execute("DROP SEQUENCE IF EXISTS change_events_sequence_number_seq")
    op.drop_table("financial_snapshots")
    op.drop_table("idempotency_keys")
