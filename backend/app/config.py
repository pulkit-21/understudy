"""Central application configuration.

Every environment knob lives here — one typed, validated, documented object
instead of `os.environ.get(...)` scattered across the codebase. Read it with
`get_settings()` (cached), or import `settings` for module-level defaults.

Two distinct models are configured on purpose (see `agent_model` vs
`induction_model`): induction is a rare, correctness-adjacent legibility pass
where the extra capability of Opus is worth it; the conversational agent is a
high-frequency, tool-driving loop where Sonnet is fast and cheap enough. Both
are overridable per-deployment.
"""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_log = logging.getLogger("understudy.config")

# Absolute path to the project-root .env, so the key is found no matter which
# directory the server is launched from (repo root, backend/, or a container
# WORKDIR). backend/app/config.py -> parents[2] is the repo root.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# The dev-only JWT secret. Committed on purpose for zero-config local runs;
# outside dev mode it's auto-replaced with a generated secret so it never signs
# real tokens (see Settings._never_ship_the_dev_secret).
DEV_JWT_SECRET = "understudy-dev-secret-change-me-in-prod-0123456789"


class Settings(BaseSettings):
    """Typed application settings, sourced from the environment (prefix
    ``UNDERSTUDY_`` where noted) with sensible local-dev defaults."""

    model_config = SettingsConfigDict(
        env_prefix="UNDERSTUDY_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,  # allow init/env by field name OR alias
    )

    # --- storage -----------------------------------------------------------
    data_dir: Path = Field(
        default=Path("./data"),
        description="Where SQLite + JSON artifacts live (UNDERSTUDY_DATA).",
    )
    # DATABASE_URL is a platform convention (Render/Heroku) — no prefix.
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    # --- web ---------------------------------------------------------------
    base_url: str = Field(
        default="http://localhost:8000",
        description="Public origin the runner navigates to (UNDERSTUDY_BASE_URL).",
    )

    # --- models ------------------------------------------------------------
    # Anthropic key is read by the SDK from ANTHROPIC_API_KEY directly; we only
    # need to know whether it's present, exposed via `has_api_key`.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    agent_model: str = Field(
        default="claude-sonnet-5",
        description="Model for the conversational agent's tool-use loop.",
    )
    induction_model: str = Field(
        default="claude-opus-4-8",
        description="Model for the one-shot workflow legibility pass "
        "(UNDERSTUDY_INDUCTION_MODEL).",
    )

    # --- runner ------------------------------------------------------------
    headful: bool = Field(
        default=False,
        description="Run Chromium with a visible window (UNDERSTUDY_HEADFUL).",
    )

    # --- auth --------------------------------------------------------------
    jwt_secret: str = Field(
        default=DEV_JWT_SECRET,
        description="HS256 signing secret (UNDERSTUDY_JWT_SECRET). Override in prod.",
    )

    # --- toggles -----------------------------------------------------------
    ratelimit: bool = Field(default=True, description="Enable request rate limiting.")
    # NoDecode: take the env value raw (a comma-separated string) rather than
    # JSON — _split_csv turns it into a list.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://localhost:8000"],
        description="Allowed CORS origins. Prod serves the SPA same-origin so "
        "needs none; set UNDERSTUDY_CORS_ORIGINS (comma-separated) for a "
        "split-origin deploy.",
    )
    agent_mock: bool = Field(
        default=False,
        description="Force the keyless deterministic agent even if a key is set.",
    )
    enable_test_hooks: bool = Field(
        default=False,
        description="Expose destructive test/eval hooks (e.g. POST /erp/_reset). "
        "Off in production; the test suite and eval harness turn it on.",
    )
    scheduler_enabled: bool = Field(
        default=False,
        description="Run the background scheduler that fires due schedules "
        "(UNDERSTUDY_SCHEDULER_ENABLED). Off in tests.",
    )
    scheduler_tick_seconds: int = Field(
        default=30, description="How often the scheduler checks for due schedules.")
    dev_mode: bool = Field(
        default=False,
        description="Explicit local-dev acknowledgement (UNDERSTUDY_DEV_MODE). "
        "Lets the committed dev JWT secret be used as-is; in production the "
        "committed default is auto-replaced with a generated one (see below).",
    )

    @model_validator(mode="after")
    def _never_ship_the_dev_secret(self) -> Settings:
        """Outside explicit dev mode, never run with the committed (public) dev
        JWT secret. If no UNDERSTUDY_JWT_SECRET was provided, mint a strong
        random one for this process so a fresh deploy works out of the box
        without ever signing tokens with a secret that's in the source tree. The
        generated secret is per-process — set UNDERSTUDY_JWT_SECRET explicitly
        for sessions that survive a restart or span multiple instances."""
        if self.jwt_secret == DEV_JWT_SECRET and not self.dev_mode:
            self.jwt_secret = secrets.token_urlsafe(48)
            _log.warning(
                "UNDERSTUDY_JWT_SECRET not set — generated an ephemeral secret "
                "for this process. Set UNDERSTUDY_JWT_SECRET for stable sessions.")
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        # accept a comma-separated env string as well as a JSON/list value
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def use_mock_agent(self) -> bool:
        return self.agent_mock or not self.has_api_key


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton. Cached so env is read once; call
    `get_settings.cache_clear()` in tests that mutate the environment."""
    return Settings()


# Convenience module-level handle for import sites that don't need the cache
# semantics. Prefer `get_settings()` in code that tests may reconfigure.
settings = get_settings()
