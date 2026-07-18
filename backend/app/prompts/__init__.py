"""LLM prompts, kept out of the code that sends them so they can be read,
diffed, and tuned in one place."""
from .agent import AGENT_SYSTEM
from .induction import INDUCTION_SYSTEM
from .locator import LOCATOR_SYSTEM

__all__ = ["AGENT_SYSTEM", "INDUCTION_SYSTEM", "LOCATOR_SYSTEM"]
