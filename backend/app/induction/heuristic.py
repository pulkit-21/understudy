"""Heuristic induction: trace -> WorkflowSpec, deterministically.

This is the baseline layer, and — deliberately — it is where the interesting
work happens. It gets the *structure* right (steps, targets, risk flags) AND
solves the two things that turn a recorded macro into a learned *procedure*,
both without any LLM:

  1. PARAMETERIZED NAVIGATION. A click that opened INV-1001 has a testid that
     bakes in that one invoice (`open-INV-1001`). When the click leads to a URL
     with a run-varying token (`/portal/invoice/INV-1001`), we rewrite it into a
     NAVIGATE to `/portal/invoice/{{invoice_id}}`. The replay opens whichever
     invoice it's asked to — not the one from the demo.

  2. PROVENANCE / LIVE EXTRACTION. A value the user TYPED into the ERP that they
     had earlier READ off a page (captured in that page's `readable_fields`)
     becomes an `extract` step targeting the *real* testid of the source element,
     plus a `{{extract.key}}` reference. The replay re-reads the value live from
     the source system instead of being handed a constant.

Together these mean the learned workflow needs only `invoice_id`: everything
else is pulled from the invoice page at run time. Because it's deterministic it
works offline, runs in CI, and is exactly testable. The LLM layer (llm.py) then
*enriches* — better phrasing, phase grouping, fuzzy provenance the exact-match
pass missed — but correctness does not depend on it.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..domain.trace import EventType, ReadableField, TargetInfo, Trace
from ..domain.workflow import (
    ActionType,
    RiskLevel,
    WorkflowParameter,
    WorkflowSpec,
    WorkflowStep,
)

COMMIT_WORDS = re.compile(
    r"\b(post|submit|pay|approve|send|confirm|transfer|create|save|record)\b", re.I)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "value"


def _looks_dynamic(value: str) -> bool:
    """Would this path segment plausibly change run-to-run? Used to spot the
    run-varying token in a URL (e.g. INV-1001 in /portal/invoice/INV-1001).
    A digit is the tell for ids/codes/dates."""
    return bool(re.search(r"\d", value))




def _extract_key(field: ReadableField) -> str:
    """A short, stable name for an extracted value, from its element testid
    (preferred) or label: 'inv-vendor' -> 'vendor', 'Invoice date' -> ..."""
    base = field.testid or field.label or field.value
    base = re.sub(r"^(inv|field|col|cell)[-_]", "", base, flags=re.I)
    return _slug(base)


def _dynamic_url_token(url: str) -> tuple[str | None, str | None]:
    """If the URL's last path segment is a run-varying token, return
    (token, param_key); else (None, None). /portal/invoice/INV-1001 ->
    ('INV-1001', 'invoice_id')."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts or not _looks_dynamic(parts[-1]):
        return None, None
    prev = parts[-2] if len(parts) >= 2 else None
    if prev and prev.isalpha():
        # a collection segment is usually plural ("payments/AP-1") -> singular key
        noun = prev[:-1] if prev.endswith("s") and len(prev) > 3 else prev
        key = f"{_slug(noun)}_id"
    else:
        key = "id"
    return parts[-1], key


def induce_heuristic(trace: Trace, name: str | None = None) -> WorkflowSpec:
    spec = WorkflowSpec(
        name=name or trace.name,
        description=f"Learned from demonstration '{trace.name}'.",
        source_trace_ids=[trace.id],
    )

    steps: list[WorkflowStep] = []
    params: dict[str, str] = {}                 # param key -> example value
    # value seen in the demo -> how a later occurrence of it should resolve.
    # ("param", key) for run inputs; ("extract", key) for values read off a page.
    value_source: dict[str, tuple[str, str]] = {}
    # value -> (anchor_step_index, field): where each readable value came from,
    # so its extract step can be inserted right after that page's navigate.
    fields_seen: dict[str, tuple[int, ReadableField]] = {}
    extracts_by_anchor: dict[int, list[WorkflowStep]] = {}
    used_extract_keys: set[str] = set()

    def record_fields(anchor: int, fields: list[ReadableField]) -> None:
        for f in fields:
            fields_seen.setdefault(f.value, (anchor, f))

    def resolve(value: str, fallback_name: str) -> str:
        """Return the templated value for a fill/select, creating extract steps
        or parameters as needed. Priority: known token -> read-off-a-page
        (extract) -> dynamic (new parameter) -> literal constant."""
        if value in value_source:
            kind, key = value_source[value]
            return f"{{{{extract.{key}}}}}" if kind == "extract" else f"{{{{{key}}}}}"
        if value in fields_seen:
            anchor, field = fields_seen[value]
            key = _extract_key(field)
            while key in used_extract_keys:
                key += "_"
            used_extract_keys.add(key)
            extracts_by_anchor.setdefault(anchor, []).append(WorkflowStep(
                intent=f"Read {field.label or key} from the source page",
                action=ActionType.EXTRACT,
                target=TargetInfo(testid=field.testid, role=field.role,
                                  name=field.name or field.label),
                extract_key=key,
                risk=RiskLevel.READ,
            ))
            value_source[value] = ("extract", key)
            return f"{{{{extract.{key}}}}}"
        # A value the operator TYPED but that isn't on any source page is a
        # per-run input -> parameter (keyed by the field). Values read off a page
        # already became extracts above; empty values fall through as literals.
        if value.strip():
            key = _slug(fallback_name)
            params.setdefault(key, value)
            value_source[value] = ("param", key)
            return f"{{{{{key}}}}}"
        return value

    events = trace.events
    i = 0
    prev_type: EventType | None = None
    while i < len(events):
        e = events[i]
        nxt = events[i + 1] if i + 1 < len(events) else None
        t = e.target

        if e.type == EventType.NAVIGATE:
            # A load right after a click/submit is that action's RESULT, not a
            # new intent — but its fields are still provenance. Attach them to
            # the most recent navigate step so their extracts land in the run.
            if prev_type in (EventType.CLICK, EventType.SUBMIT):
                anchor = len(steps) - 1
                record_fields(anchor if anchor >= 0 else 0, e.readable_fields)
                prev_type = e.type
                i += 1
                continue
            steps.append(WorkflowStep(
                intent=f"Open {e.page_title or urlparse(e.url).path}",
                action=ActionType.NAVIGATE, url=e.url, risk=RiskLevel.READ,
            ))
            record_fields(len(steps) - 1, e.readable_fields)

        elif e.type == EventType.CLICK:
            # Click that opens a run-varying URL -> parameterized navigate, so
            # the replay opens the requested record, not the demonstrated one.
            token, key = (
                _dynamic_url_token(nxt.url)
                if nxt and nxt.type == EventType.NAVIGATE and nxt.url != e.url
                else (None, None)
            )
            if token and key:
                assert nxt is not None  # token is set only when nxt is a navigate
                params.setdefault(key, token)
                value_source[token] = ("param", key)
                noun = urlparse(nxt.url).path.strip("/").split("/")[-2] or "page"
                steps.append(WorkflowStep(
                    intent=f"Open {noun} {{{{{key}}}}}",
                    action=ActionType.NAVIGATE,
                    # replace ONLY the final path segment (the run-varying id),
                    # not every occurrence — a short/numeric id can recur earlier
                    # in the path (e.g. /portal/v1/invoice/1).
                    url=f"{{{{{key}}}}}".join(nxt.url.rsplit(token, 1)),
                    risk=RiskLevel.READ,
                ))
                record_fields(len(steps) - 1, nxt.readable_fields)
                prev_type = EventType.NAVIGATE
                i += 2                      # consume the click AND its navigation
                continue
            assert t is not None
            # A click whose label reads like a commit ("Pay", "Confirm", …) —
            # e.g. an action link rather than a form submit — is gated too.
            commit_click = bool(COMMIT_WORDS.search(t.name or ""))
            steps.append(WorkflowStep(
                intent=f"Click {t.describe()}",
                action=ActionType.CLICK, target=t,
                risk=RiskLevel.COMMIT if commit_click else RiskLevel.READ,
                requires_approval=commit_click,
            ))

        elif e.type in (EventType.FILL, EventType.SELECT):
            assert t is not None and e.value is not None
            value = resolve(e.value, t.name or t.testid or "field")
            steps.append(WorkflowStep(
                intent=f"Enter value into {t.describe()}",
                action=(ActionType.SELECT if e.type == EventType.SELECT
                        else ActionType.FILL),
                target=t, value=value, risk=RiskLevel.WRITE,
            ))

        elif e.type == EventType.SUBMIT:
            assert t is not None
            # A form SUBMIT is irreversible by definition — ALWAYS gate it,
            # regardless of the button's wording. (The earlier heuristic only
            # gated submits whose label matched COMMIT_WORDS, so a submit button
            # labelled "Finish"/"Go" slipped through ungated — a real safety
            # hole, and one that would let a dry run actually commit.)
            steps.append(WorkflowStep(
                intent=f"Submit the form via {t.describe()}",
                action=ActionType.CLICK, target=t,
                risk=RiskLevel.COMMIT, requires_approval=True,
            ))

        prev_type = e.type
        i += 1

    # Splice each page's extract steps in right after that page's navigate, so
    # they run while the source page is loaded and before its values are used.
    final: list[WorkflowStep] = []
    for idx, step in enumerate(steps):
        final.append(step)
        final.extend(extracts_by_anchor.get(idx, []))
    spec.steps = final

    spec.parameters = [
        WorkflowParameter(
            key=key,
            description=f"Value entered during demonstration (example: {ex})",
            example=ex,
        )
        for key, ex in params.items()
    ]
    return spec
