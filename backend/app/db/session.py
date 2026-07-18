"""Database engine + session factory.

One knob: DATABASE_URL. Unset -> SQLite under UNDERSTUDY_DATA (zero-ops, the
demo default; the file is ephemeral-by-design on redeploy). Set to a
postgres:// URL -> Postgres (managed, durable). The `postgres://` ->
`postgresql://` fixup handles Render/Heroku-style URLs that SQLAlchemy 2.x
rejects. The repository layer is written against the ORM, so nothing above the
db package changes when you switch backends.
"""
from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

DATA_DIR = get_settings().data_dir


def resolve_url() -> str:
    url = get_settings().database_url
    if url:
        # Normalize any Postgres URL onto the psycopg (v3) driver, which is the
        # one we ship (see requirements.txt). Render/Heroku hand out
        # `postgres://`; SQLAlchemy 2.x also needs an explicit driver, else it
        # defaults to psycopg2 (not installed) and boot fails.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATA_DIR / 'understudy.db'}"


def make_engine(url: str | None = None) -> Engine:
    url = url or resolve_url()
    # SQLite: check_same_thread=False (endpoints + run executor share the pool
    # across threads; safe because every repo call uses its own short-lived
    # session) and a 30s busy timeout so concurrent runs wait out a writer's
    # lock instead of raising "database is locked".
    connect_args = (
        {"check_same_thread": False, "timeout": 30}
        if url.startswith("sqlite") else {}
    )
    return create_engine(url, connect_args=connect_args, future=True)


engine: Engine = make_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False,
                            future=True)
