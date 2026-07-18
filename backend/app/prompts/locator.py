"""System prompt for the last-resort LLM locator fallback (engine.PlaywrightSink).

Fires only when the deterministic chain (testid -> role+name -> css) has failed —
e.g. a redesign renamed the test id AND the accessible name. The model sees the
target we're looking for and the page's interactive elements, and returns one
CSS selector."""

LOCATOR_SYSTEM = """\
You resolve a UI target after a site redesign broke its recorded selectors.
You are given a JSON object with:
  - "target": how the element was identified when recorded (role, name, testid,
    tag) — what we're trying to find again,
  - "candidates": the page's current interactive elements (tag, text, id, name,
    placeholder, aria-label, role, data-testid).

Return ONLY a single CSS selector that uniquely identifies the SAME element on
the current page — nothing else, no prose, no code fences. Prefer a stable,
specific selector (an id, a name attribute, or a unique text/role). If no
candidate is a confident match, return exactly: NONE
"""
