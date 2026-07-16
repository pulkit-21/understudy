"""Heuristic induction: trace -> WorkflowSpec, deterministically.

This is the baseline layer. It gets the *structure* right (steps, targets,
risk flags, obvious parameters) without any LLM, which means:
  * the end-to-end loop works offline and in CI,
  * induction has a floor of quality the LLM can only improve on,
  * snapshot tests are exact, not fuzzy.

The LLM layer (llm.py) then enriches: better intent phrasing, smarter
parameter naming, and — its unique contribution — EXTRACT steps that link a
typed value back to the page it was read from (provenance), so a replay can
pull fresh values from the source system instead of re-typing constants.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models.trace import EventType, SemanticEvent, Trace
from ..models.workflow import (
    ActionType,
    RiskLevel,
    WorkflowParameter,
    WorkflowSpec,
    WorkflowStep,
)

COMMIT_WORDS = re.compile(r"\b(post|submit|pay|approve|send|confirm|transfer)\b", re.I)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "value"


def _looks_dynamic(value: str) -> bool:
    """Would this value plausibly change run-to-run?

    Numbers, dates, ids and codes are per-run data; short pure-alpha words
    (like a GL description) may be constants. Deliberately conservative —
    over-parameterizing is safer than baking one demo's data into the spec.
    """
    return bool(re.search(r"\d", value))


def induce_heuristic(trace: Trace, name: str | None = None) -> WorkflowSpec:
    spec = WorkflowSpec(
        name=name or trace.name,
        description=f"Learned from demonstration '{trace.name}'.",
        source_trace_ids=[trace.id],
    )
    seen_params: dict[str, str] = {}  # param key -> example value
    prev_type: EventType | None = None

    for event in trace.events:
        step = _event_to_step(event, prev_type, seen_params)
        if step is not None:
            spec.steps.append(step)
        prev_type = event.type

    spec.parameters = [
        WorkflowParameter(
            key=key,
            description=f"Value entered during demonstration (example: {ex})",
            example=ex,
        )
        for key, ex in seen_params.items()
    ]
    return spec


def _event_to_step(
    event: SemanticEvent,
    prev_type: EventType | None,
    seen_params: dict[str, str],
) -> WorkflowStep | None:
    t = event.target

    if event.type == EventType.NAVIGATE:
        # A page load right after a click/submit is the RESULT of that action,
        # not a new intent. A load with no preceding action (first page, typed
        # URL, bookmark) is a genuine "go there" step — dropping it would
        # strand the replay on the previous page.
        if prev_type in (EventType.CLICK, EventType.SUBMIT):
            return None
        return WorkflowStep(
            intent=f"Open {event.page_title or urlparse(event.url).path}",
            action=ActionType.NAVIGATE,
            url=event.url,
            risk=RiskLevel.READ,
        )

    if event.type == EventType.CLICK:
        assert t is not None
        return WorkflowStep(
            intent=f"Click {t.describe()}",
            action=ActionType.CLICK,
            target=t,
            risk=RiskLevel.READ,
        )

    if event.type in (EventType.FILL, EventType.SELECT):
        assert t is not None and event.value is not None
        value: str = event.value
        if _looks_dynamic(value):
            key = _slug(t.name or t.testid or "field")
            seen_params.setdefault(key, value)
            value = f"{{{{{key}}}}}"
        action = (ActionType.SELECT if event.type == EventType.SELECT
                  else ActionType.FILL)
        return WorkflowStep(
            intent=f"Enter value into {t.describe()}",
            action=action,
            target=t,
            value=value,
            risk=RiskLevel.WRITE,
        )

    if event.type == EventType.SUBMIT:
        assert t is not None
        is_commit = bool(COMMIT_WORDS.search(t.name or ""))
        return WorkflowStep(
            intent=f"Submit the form via {t.describe()}",
            action=ActionType.CLICK,
            target=t,
            risk=RiskLevel.COMMIT if is_commit else RiskLevel.WRITE,
            requires_approval=is_commit,   # fintech default: gate commits
        )

    return None
