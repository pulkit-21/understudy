"""Shared slowapi limiter. Attached to the app in main.py; endpoints opt in
with @limiter.limit(...). Protects auth (credential stuffing) and the expensive
run/induce endpoints."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .config import get_settings


def _client_key(request: Request) -> str:
    """Rate-limit per real client. Behind a reverse proxy (Render), the socket
    peer is the proxy — so every client would share one bucket and one attacker
    could lock everyone out. Prefer the left-most X-Forwarded-For hop. (It's
    client-spoofable, but the only downside of a spoofed key is that the
    attacker throttles their own made-up identity — strictly better than a
    single shared bucket.)"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


# Disable in the test suite (UNDERSTUDY_RATELIMIT=0) so repeated endpoint hits
# across tests don't trip the limit.
limiter = Limiter(key_func=_client_key, default_limits=[],
                  enabled=get_settings().ratelimit)
