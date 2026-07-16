"""Database engine + session factory.

One knob: DATABASE_URL. Unset -> SQLite under UNDERSTUDY_DATA (zero-ops, the
demo default; the file is ephemeral-by-design on redeploy). Set to a
postgres:// URL -> Postgres (managed, durable). The `postgres://` ->
`postgresql://` fixup handles Render/Heroku-style URLs that SQLAlchemy 2.x
rejects. The repository layer is written against the ORM, so nothing above the
db package changes when you switch backends.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DATA_DIR = Path(os.environ.get("UNDERSTUDY_DATA", "./data"))


def resolve_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):  # Render/Heroku dialect fixup
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATA_DIR / 'understudy.db'}"


def make_engine(url: str | None = None) -> Engine:
    url = url or resolve_url()
    # check_same_thread=False: our async endpoints and the run executor touch
    # the same SQLite connection pool across threads; safe here because every
    # repository call uses its own short-lived session.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine: Engine = make_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False,
                            future=True)
