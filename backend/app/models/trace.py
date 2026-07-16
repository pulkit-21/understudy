"""Semantic trace models.

A Trace is what the recorder produces: an ordered list of *semantic* events
(what the user did, expressed in terms of accessible roles/labels), not pixel
coordinates or raw DOM mutations. This is the input to workflow induction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"          # final value of a text-like input (inputs collapsed)
    SELECT = "select"      # <select> choice
    SUBMIT = "submit"      # form submission


class TargetInfo(BaseModel):
    """How the user's target element is identified, most-semantic first.

    The executor resolves targets in this order: testid -> role+name -> css.
    Keeping all three captured at record time is what makes replays survive
    cosmetic DOM changes (self-healing fallback chain).
    """

    role: Optional[str] = None          # ARIA role, e.g. "button", "textbox"
    name: Optional[str] = None          # accessible name / label text
    testid: Optional[str] = None        # data-testid, most stable when present
    css: Optional[str] = None           # generated CSS selector, last resort
    tag: Optional[str] = None           # html tag, for debugging/heuristics

    def describe(self) -> str:
        if self.name and self.role:
            return f"{self.role} '{self.name}'"
        return self.testid or self.css or self.tag or "unknown element"


class SemanticEvent(BaseModel):
    type: EventType
    url: str
    ts_ms: int = Field(description="epoch millis at capture time")
    target: Optional[TargetInfo] = None
    value: Optional[str] = None         # fill/select value
    page_title: Optional[str] = None
    page_text: Optional[str] = None     # trimmed innerText snapshot on NAVIGATE
                                        # -> lets induction link filled values
                                        #    back to where they were *read from*
                                        #    (data provenance / extract steps)


class Trace(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str = "untitled demonstration"
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    start_url: Optional[str] = None
    events: list[SemanticEvent] = Field(default_factory=list)

    def condensed(self, max_page_text: int = 800) -> "Trace":
        """Copy with page_text trimmed — used when building LLM prompts."""
        t = self.model_copy(deep=True)
        for e in t.events:
            if e.page_text and len(e.page_text) > max_page_text:
                e.page_text = e.page_text[:max_page_text] + " …[truncated]"
        return t
