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

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the project-root .env, so the key is found no matter which
# directory the server is launched from (repo root, backend/, or a container
# WORKDIR). backend/app/config.py -> parents[2] is the repo root.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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
        default="understudy-dev-secret-change-me-in-prod-0123456789",
        description="HS256 signing secret (UNDERSTUDY_JWT_SECRET). Override in prod.",
    )

    # --- toggles -----------------------------------------------------------
    ratelimit: bool = Field(default=True, description="Enable request rate limiting.")
    agent_mock: bool = Field(
        default=False,
        description="Force the keyless deterministic agent even if a key is set.",
    )

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
