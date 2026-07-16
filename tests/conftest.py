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

import pytest

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


@pytest.fixture()
def demo_trace() -> Trace:
    return build_demo_trace(base=BASE)
