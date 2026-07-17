"""Auth endpoints: register, login, me. Rate-limited to blunt credential
stuffing. Registration creates a personal org so the user is immediately a
tenant with their own isolated data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator

from ..auth import AuthRepo, User, current_user, issue_token
from ..ratelimit import limiter


class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    name: str = ""

    @field_validator("password")
    @classmethod
    def _min_len(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    user: User


def build_auth_router(auth: AuthRepo) -> APIRouter:
    r = APIRouter(prefix="/api/auth", tags=["auth"])

    @r.post("/register", response_model=TokenResponse)
    @limiter.limit("10/minute")
    def register(request: Request, body: RegisterBody):
        if auth.email_exists(body.email):
            raise HTTPException(409, "an account with that email already exists")
        org = auth.create_org(name=f"{body.name or body.email}'s workspace")
        user = auth.create_user(body.email, body.password,
                                body.name or body.email.split("@")[0], org.id)
        return TokenResponse(token=issue_token(user), user=user)

    @r.post("/login", response_model=TokenResponse)
    @limiter.limit("10/minute")
    def login(request: Request, body: LoginBody):
        user = auth.authenticate(body.email, body.password)
        if user is None:
            raise HTTPException(401, "wrong email or password")
        return TokenResponse(token=issue_token(user), user=user)

    @r.get("/me", response_model=User)
    def me(user: User = Depends(current_user)):
        return user

    return r
