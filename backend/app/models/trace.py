"""Semantic trace models.

A Trace is what the recorder produces: an ordered list of *semantic* events
(what the user did, expressed in terms of accessible roles/labels), not pixel
coordinates or raw DOM mutations. This is the input to workflow induction.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
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

    role: str | None = None          # ARIA role, e.g. "button", "textbox"
    name: str | None = None          # accessible name / label text
    testid: str | None = None        # data-testid, most stable when present
    css: str | None = None           # generated CSS selector, last resort
    tag: str | None = None           # html tag, for debugging/heuristics

    def describe(self) -> str:
        if self.name and self.role:
            return f"{self.role} '{self.name}'"
        return self.testid or self.css or self.tag or "unknown element"


class ReadableField(BaseModel):
    """A labelled value the recorder saw on a page (a data-testid'd element and
    its text). Captured on NAVIGATE alongside page_text so induction can turn a
    value that was READ here and TYPED later into an `extract` step that targets
    this element's REAL testid — provenance without inventing selectors."""

    testid: str | None = None
    label: str | None = None         # dt/label/aria text next to the value
    value: str                          # the visible text that was read
    role: str | None = None
    name: str | None = None


class SemanticEvent(BaseModel):
    type: EventType
    url: str
    ts_ms: int = Field(description="epoch millis at capture time")
    target: TargetInfo | None = None
    value: str | None = None         # fill/select value
    page_title: str | None = None
    page_text: str | None = None     # trimmed innerText snapshot on NAVIGATE
                                        # -> human-readable provenance context
    readable_fields: list[ReadableField] = Field(default_factory=list)
                                        # structured provenance: labelled,
                                        # testid'd values seen on this page ->
                                        # the source of `extract` step targets


class Trace(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str = "untitled demonstration"
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    start_url: str | None = None
    events: list[SemanticEvent] = Field(default_factory=list)

    def condensed(self, max_page_text: int = 800) -> Trace:
        """Copy with page_text trimmed — used when building LLM prompts."""
        t = self.model_copy(deep=True)
        for e in t.events:
            if e.page_text and len(e.page_text) > max_page_text:
                e.page_text = e.page_text[:max_page_text] + " …[truncated]"
        return t
