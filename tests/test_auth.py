"""Auth + tenant isolation through the HTTP layer."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register(email, password="password123", name="X"):
    return client.post("/api/auth/register",
                       json={"email": email, "password": password, "name": name})


def test_register_returns_token_and_user():
    r = _register("a@example.com")
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == "a@example.com"
    assert body["user"]["org_id"].startswith("org-")


def test_duplicate_email_is_409():
    _register("dup@example.com")
    assert _register("dup@example.com").status_code == 409


def test_weak_password_is_422():
    r = client.post("/api/auth/register",
                    json={"email": "w@example.com", "password": "short"})
    assert r.status_code == 422


def test_login_and_me():
    _register("b@example.com", "password123")
    bad = client.post("/api/auth/login",
                      json={"email": "b@example.com", "password": "wrong"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login",
                     json={"email": "b@example.com", "password": "password123"})
    assert ok.status_code == 200
    token = ok.json()["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "b@example.com"
    assert client.get("/api/auth/me").status_code == 401  # no token


def test_tenants_are_isolated_over_http():
    """Org A creates a trace; org B must not see or fetch it."""
    a = _register("owner-a@example.com").json()["token"]
    b = _register("owner-b@example.com").json()["token"]
    ha = {"Authorization": f"Bearer {a}"}
    hb = {"Authorization": f"Bearer {b}"}

    trace = {"id": "t-secret", "name": "A's trace", "events": []}
    assert client.post("/api/traces", json=trace, headers=ha).status_code == 200

    # A sees it; B does not
    assert any(t["id"] == "t-secret"
               for t in client.get("/api/traces", headers=ha).json())
    assert client.get("/api/traces", headers=hb).json() == []
    assert client.get("/api/traces/t-secret", headers=hb).status_code == 404


def test_sse_stream_ticket_is_scoped_and_not_a_bearer(org_id):
    """H2: the SSE ticket is short-lived, bound to one run, and one-directional —
    it can't be replayed as a general bearer, and a bearer can't act as a ticket."""
    from app.auth import (
        issue_token,
        mint_stream_ticket,
        user_from_stream_ticket,
        user_from_token,
    )
    from app.main import auth

    user = auth.create_user("sse-scope@example.com", "password123", "S", org_id)
    ticket = mint_stream_ticket(user, "run-123")

    # valid only for the run it was minted for
    assert user_from_stream_ticket(ticket, "run-123").id == user.id
    assert user_from_stream_ticket(ticket, "run-999") is None
    # a leaked ticket is NOT a general credential
    assert user_from_token(ticket) is None
    # and a normal bearer token is NOT accepted as a stream ticket
    assert user_from_stream_ticket(issue_token(user), "run-123") is None
