"""The LLM client — the single place the Anthropic SDK is constructed.

Both callers (the workflow-legibility pass and the conversational agent) build
their client here, so the key handling lives in one spot: the key comes from
Settings, which may have sourced it from `.env` — a path the SDK's default
`os.environ` lookup would miss. The import is lazy so `anthropic` stays an
optional dependency; callers that support a keyless/offline mode catch
`LLMUnavailable`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import get_settings

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic


class LLMUnavailable(RuntimeError):
    """Raised when the Anthropic SDK isn't installed or no key is configured."""


def anthropic_client() -> AsyncAnthropic:
    settings = get_settings()
    if not settings.has_api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - the SDK is a declared dep
        raise LLMUnavailable("anthropic SDK not installed") from e
    return AsyncAnthropic(api_key=settings.anthropic_api_key)
