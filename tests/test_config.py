"""The central Settings object: env resolution, model split, derived flags."""
from __future__ import annotations

import pytest

from app.config import Settings


def test_defaults_split_agent_and_induction_models():
    """The conversational agent runs on Sonnet (cheap, high-frequency); the
    one-shot induction legibility pass runs on Opus."""
    s = Settings(_env_file=None)
    assert s.agent_model == "claude-sonnet-5"
    assert s.induction_model == "claude-opus-4-8"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_AGENT_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    s = Settings(_env_file=None)
    assert s.agent_model == "claude-haiku-4-5-20251001"
    assert s.database_url == "postgresql://x/y"


def test_use_mock_agent_when_no_key():
    s = Settings(_env_file=None, anthropic_api_key=None)
    assert s.has_api_key is False
    assert s.use_mock_agent is True


def test_use_mock_agent_forced_even_with_key():
    s = Settings(_env_file=None, anthropic_api_key="sk-test", agent_mock=True)
    assert s.has_api_key is True
    assert s.use_mock_agent is True


def test_real_agent_when_key_present():
    s = Settings(_env_file=None, anthropic_api_key="sk-test", agent_mock=False)
    assert s.use_mock_agent is False


def test_bool_toggles_parse_from_string(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_RATELIMIT", "0")
    monkeypatch.setenv("UNDERSTUDY_HEADFUL", "1")
    s = Settings(_env_file=None)
    assert s.ratelimit is False
    assert s.headful is True


def test_resolve_url_forces_the_psycopg_driver(monkeypatch):
    """A Postgres DATABASE_URL is normalized onto the psycopg (v3) driver we
    ship, so boot doesn't fail selecting the absent psycopg2 dialect."""
    from app.config import get_settings
    from app.db.session import resolve_url

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    get_settings.cache_clear()
    assert resolve_url() == "postgresql+psycopg://u:p@h:5432/db"
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    get_settings.cache_clear()
    assert resolve_url() == "postgresql+psycopg://u:p@h/db"


def test_require_secure_is_fail_closed_on_dev_secret():
    from app.config import DEV_JWT_SECRET, Settings

    # production (dev_mode off) + committed dev secret -> refuse to boot
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, jwt_secret=DEV_JWT_SECRET,
                 dev_mode=False).require_secure()
    # explicit dev mode with the dev secret is fine
    Settings(_env_file=None, jwt_secret=DEV_JWT_SECRET,
             dev_mode=True).require_secure()
    # a real secret in production is fine
    Settings(_env_file=None, jwt_secret="a-real-strong-secret",
             dev_mode=False).require_secure()
