"""Shared fixtures.

demo_trace is a faithful, hand-built replica of what inject.js emits when a
user demonstrates: open portal -> open INV-1001 -> (read values) -> go to ERP
-> fill the bill form -> post. It doubles as the seed demonstration for the
deployed demo, so tests and demo exercise the same data path.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# Point the whole suite at an isolated temp DB + data dir BEFORE any app module
# imports the engine. Without this, tests would read/write the real ./data
# store (the clutter bug we hit in Day 3). conftest is imported before test
# modules, so setting these here is early enough.
_TMP = tempfile.mkdtemp(prefix="understudy-test-")
os.environ.setdefault("UNDERSTUDY_DATA", _TMP)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("UNDERSTUDY_RATELIMIT", "0")  # don't throttle across tests
# Hermetic by default: the whole suite runs the deterministic keyless agent so a
# developer's real ANTHROPIC_API_KEY (loaded from .env by Settings) never causes
# a live API call during tests. The LLM loop is exercised only outside CI.
os.environ.setdefault("UNDERSTUDY_AGENT_MOCK", "1")

import pytest

# Import the app once at collection time so its module-level run_migrations()
# provisions the schema BEFORE the _clean_db fixture ever runs create_all —
# otherwise, in an isolated run, Alembic would try to create tables that
# _clean_db already made.
import app.main  # noqa: F401
from app.db import Base, engine
from app.models.trace import Trace
from app.seed import build_demo_trace

BASE = "http://localhost:8000"


@pytest.fixture(autouse=True)
def _clean_db():
    """Fresh schema per test — isolation without migration overhead."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Settings are process-cached (lru_cache). Clear the cache around each test
    so a test's monkeypatched env is read fresh and never leaks to the next."""
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def demo_trace() -> Trace:
    return build_demo_trace(base=BASE)


@pytest.fixture()
def org_id() -> str:
    """A fresh tenant for a test."""
    from app.main import auth
    return auth.create_org("test-org").id


@pytest.fixture()
def authed_client(org_id):
    """A TestClient with a valid bearer token for a fresh user in `org_id`.
    Returns (client, org_id)."""
    from fastapi.testclient import TestClient

    from app.auth import issue_token
    from app.main import app, auth

    user = auth.create_user("tester@example.com", "password123", "Tester",
                            org_id)
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {issue_token(user)}"})
    return client, org_id
