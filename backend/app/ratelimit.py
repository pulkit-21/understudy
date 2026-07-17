"""Shared slowapi limiter. Attached to the app in main.py; endpoints opt in
with @limiter.limit(...). Protects auth (credential stuffing) and the expensive
run/induce endpoints."""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Disable in the test suite (UNDERSTUDY_RATELIMIT=0) so repeated endpoint hits
# across tests don't trip the limit.
_enabled = os.environ.get("UNDERSTUDY_RATELIMIT", "1") != "0"
limiter = Limiter(key_func=get_remote_address, default_limits=[],
                  enabled=_enabled)
