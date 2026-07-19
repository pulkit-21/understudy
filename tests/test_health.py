"""The /healthz readiness probe.

It backs Render's healthCheckPath, so it must be a real readiness check: 200
only when the DB answers, 503 (so the instance is pulled from rotation) when it
doesn't — never a blind "ok".
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_reports_ready_when_db_is_up():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": "up"}


def test_healthz_returns_503_when_db_is_unreachable(monkeypatch):
    """A failing DB round-trip must surface as unhealthy, not a false 200."""
    import app.main as main

    class _Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(main, "SessionLocal", lambda: _Boom(), raising=False)
    # patch the symbol the handler imports lazily from db.session
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: _Boom())

    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False and body["db"] == "down"
