"""Authentication + tenancy primitives.

bcrypt password hashing, HS256 JWTs, and a `current_user` FastAPI dependency
that every data endpoint depends on. The user's org_id is the tenancy key —
repositories filter and stamp by it, so one org can never read another's traces,
workflows, or runs.
"""
from __future__ import annotations

import os
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

from .db.models import OrgRow, UserRow

# Dev default is ≥32 bytes (SHA-256 min); override with UNDERSTUDY_JWT_SECRET
# in any real deployment.
JWT_SECRET = os.environ.get(
    "UNDERSTUDY_JWT_SECRET", "understudy-dev-secret-change-me-in-prod-0123456789")
JWT_ALG = "HS256"
TOKEN_TTL = timedelta(days=7)

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
            if row is None or not verify_password(password, row.password_hash):
                return None
            return User(id=row.id, email=row.email, name=row.name,
                        org_id=row.org_id)

    def get_user(self, user_id: str) -> User | None:
        with self._sf() as s:
            row = s.get(UserRow, user_id)
            return (User(id=row.id, email=row.email, name=row.name,
                         org_id=row.org_id) if row else None)


# ---- FastAPI dependency ------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)
# set by main.py once the session factory exists
_auth_repo: AuthRepo | None = None


def bind_auth_repo(repo: AuthRepo) -> None:
    global _auth_repo
    _auth_repo = repo


def user_from_token(token: str) -> User | None:
    """Resolve a raw JWT to a user, or None. Used by the SSE endpoint, where the
    browser EventSource API can't send an Authorization header so the token
    arrives as a query param instead."""
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
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
