"""
Alembic migration environment.

Uses psycopg2 (sync) for migrations — asyncpg cannot drive Alembic directly.
`include_schemas` + `include_name` are wired to detect all models registered
under the shared metadata object.

To create a migration:
    alembic revision --autogenerate -m "describe change here"

To apply:
    alembic upgrade head

To rollback one step:
    alembic downgrade -1
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Load all models so Alembic can detect them via metadata
from app.database.base import Base  # noqa: F401 — side-effects: registers metadata
import app.modules.users.models  # noqa: F401
import app.modules.customers.models  # noqa: F401
import app.modules.vouchers.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.finance.models  # noqa: F401
import app.modules.production.models  # noqa: F401
import app.modules.expenses.models  # noqa: F401
import app.modules.audit.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override DSN from environment (docker-compose passes these)
_section = config.config_ini_section
config.set_section_option(_section, "POSTGRES_USER", os.environ.get("POSTGRES_USER", "bonbon_user"))
config.set_section_option(_section, "POSTGRES_PASSWORD", os.environ.get("POSTGRES_PASSWORD", ""))
config.set_section_option(_section, "POSTGRES_HOST", os.environ.get("POSTGRES_HOST", "localhost"))
config.set_section_option(_section, "POSTGRES_PORT", os.environ.get("POSTGRES_PORT", "5432"))
config.set_section_option(_section, "POSTGRES_DB", os.environ.get("POSTGRES_DB", "bonbon_oil_db"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
