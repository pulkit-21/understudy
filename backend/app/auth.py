"""Authentication + tenancy primitives.

bcrypt password hashing, HS256 JWTs, and a `current_user` FastAPI dependency
that every data endpoint depends on. The user's org_id is the tenancy key —
repositories filter and stamp by it, so one org can never read another's traces,
workflows, or runs.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db.models import OrgRow, UserRow

# Dev default is ≥32 bytes (SHA-256 min); override with UNDERSTUDY_JWT_SECRET
# in any real deployment.
JWT_SECRET = get_settings().jwt_secret
JWT_ALG = "HS256"
TOKEN_TTL = timedelta(days=7)
# Short-lived, single-run, read-only ticket for the SSE stream. EventSource can't
# send an Authorization header, so a credential must ride in the URL — but the
# 7-day bearer JWT there would leak into logs/history and be replayable against
# the whole API. This ticket is scoped to one run and expires in a minute.
STREAM_TICKET_TTL = timedelta(minutes=1)

SessionFactory = Callable[[], Session]


class User(BaseModel):
    id: str
    email: str
    name: str
    org_id: str


class Org(BaseModel):
    id: str
    name: str


# ---- password hashing --------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


# A real bcrypt hash compared against on the unknown-email login path, so an
# absent account costs the same wall-clock as a present one (no timing oracle).
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


# ---- tokens ------------------------------------------------------------------

def issue_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user.id, "org": user.org_id, "email": user.email,
               "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


# ---- user / org repository ---------------------------------------------------

def _now() -> datetime:
    return datetime.now(UTC)


class AuthRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def create_org(self, name: str) -> Org:
        with self._sf() as s:
            row = OrgRow(id="org-" + uuid4().hex[:10], name=name,
                         created_at=_now())
            s.add(row)
            s.commit()
            return Org(id=row.id, name=row.name)

    def create_user(self, email: str, password: str, name: str,
                    org_id: str) -> User:
        with self._sf() as s:
            row = UserRow(id="usr-" + uuid4().hex[:10], email=email.lower(),
                          password_hash=hash_password(password), name=name,
                          org_id=org_id, created_at=_now())
            s.add(row)
            s.commit()
            return User(id=row.id, email=row.email, name=row.name,
                        org_id=row.org_id)

    def _row_by_email(self, s: Session, email: str) -> UserRow | None:
        return s.execute(
            select(UserRow).where(UserRow.email == email.lower())
        ).scalar_one_or_none()

    def email_exists(self, email: str) -> bool:
        with self._sf() as s:
            return self._row_by_email(s, email) is not None

    def authenticate(self, email: str, password: str) -> User | None:
        with self._sf() as s:
            row = self._row_by_email(s, email)
            # Always run a bcrypt comparison, even when the email is unknown, so
            # login timing doesn't reveal which emails have accounts.
            hashed = row.password_hash if row is not None else _DUMMY_HASH
            ok = verify_password(password, hashed)
            if row is None or not ok:
                return None
            return User(id=row.id, email=row.email, name=row.name,
                        org_id=row.org_id)

    def get_user(self, user_id: str) -> User | None:
        with self._sf() as s:
            row = s.get(UserRow, user_id)
            return (User(id=row.id, email=row.email, name=row.name,
                         org_id=row.org_id) if row else None)

    def list_org(self, org_id: str) -> list[dict]:
        with self._sf() as s:
            rows = s.execute(
                select(UserRow).where(UserRow.org_id == org_id)
                .order_by(UserRow.created_at)
            ).scalars().all()
            return [{"id": r.id, "email": r.email, "name": r.name,
                     "created_at": r.created_at} for r in rows]


# ---- FastAPI dependency ------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)
# set by main.py once the session factory exists
_auth_repo: AuthRepo | None = None


def bind_auth_repo(repo: AuthRepo) -> None:
    global _auth_repo
    _auth_repo = repo


def user_from_token(token: str) -> User | None:
    """Resolve a raw bearer JWT to a user, or None. Rejects SSE stream tickets
    (typ=sse) so a leaked ticket can't be replayed as a general credential."""
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("typ") == "sse":
        return None
    assert _auth_repo is not None
    return _auth_repo.get_user(payload.get("sub", ""))


def mint_stream_ticket(user: User, run_id: str) -> str:
    """A short-lived JWT scoped to one run's SSE stream (typ=sse). It cannot be
    replayed against the rest of the API — see user_from_stream_ticket."""
    now = datetime.now(UTC)
    payload = {"sub": user.id, "run": run_id, "typ": "sse",
               "iat": now, "exp": now + STREAM_TICKET_TTL}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def user_from_stream_ticket(ticket: str, run_id: str) -> User | None:
    """Resolve an SSE ticket to a user, but only for the run it was minted for.
    Rejects ordinary bearer JWTs (they lack typ=sse), so a leaked ticket can't
    be used as a general credential and vice-versa."""
    try:
        payload = decode_token(ticket)
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "sse" or payload.get("run") != run_id:
        return None
    assert _auth_repo is not None
    return _auth_repo.get_user(payload.get("sub", ""))


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(401, "not authenticated")
    user = user_from_token(creds.credentials)
    if user is None:
        raise HTTPException(401, "invalid token or user no longer exists")
    return user
