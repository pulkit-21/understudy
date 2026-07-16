"""Alembic environment. Online mode only (we always have a real URL)."""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the app package importable when Alembic is run via the CLI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.engine import resolve_url  # noqa: E402
from app.db.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:  # noqa: BLE001 — logging config is optional
        pass

# Prefer an injected URL (app/db/migrate.py sets it), else fall back to resolve.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", resolve_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # render_as_batch: SQLite can't ALTER; batch mode makes future
        # migrations portable across SQLite and Postgres.
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
