"""Run Alembic migrations programmatically (on app boot and in tests).

Alembic is the schema source of truth; calling it in-process means a fresh
deploy provisions its own schema with no extra shell step. `script_location`
and `sqlalchemy.url` are injected so this works regardless of cwd.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .engine import resolve_url

_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"


def _config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", resolve_url())
    return cfg


def run_migrations() -> None:
    command.upgrade(_config(), "head")
