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


def parse_locator_reply(text: str) -> str | None:
    """Pull a CSS selector out of the model's reply (pure — unit-tested).
    Accepts a bare selector, a ```-fenced one, or a JSON {"css": "..."}; returns
    None for an explicit NONE / empty / obviously-invalid answer."""
    import json as _json

    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").split("\n", 1)[-1].strip()
    if t.startswith("{"):
        try:
            t = str(_json.loads(t).get("css", "")).strip()
        except Exception:
            return None
    t = t.splitlines()[0].strip() if t else ""
    if not t or t.upper() == "NONE" or len(t) > 300:
        return None
    return t


async def propose_locator(target: dict, candidates: list[dict]) -> str | None:
    """Last-resort locator: ask the LLM for a CSS selector matching `target`
    given the page's interactive elements. Returns None if the LLM is
    unavailable or declines — the caller then fails the step (deterministic
    behavior is never worsened by this)."""
    from ..prompts import LOCATOR_SYSTEM
    from .llm import LLMUnavailable  # local: keep import graph obvious

    try:
        client = anthropic_client()
    except LLMUnavailable:
        return None
    import json
    msg = await client.messages.create(
        model=get_settings().agent_model, max_tokens=200, system=LOCATOR_SYSTEM,
        messages=[{"role": "user",
                   "content": json.dumps({"target": target, "candidates": candidates})}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return parse_locator_reply(text)
