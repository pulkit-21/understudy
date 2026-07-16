"""The Workflow Spec — Understudy's intermediate representation.

Design goals (in priority order):
 1. LEGIBLE   — every step carries a natural-language `intent`; a finance
                reviewer can read the whole procedure without knowing HTML.
 2. EDITABLE  — plain JSON, rendered as an editable list in the UI; steps can
                be renamed, re-ordered, deleted, or flagged for approval.
 3. PARAMETERIZED — the induction step separates *what varies per run*
                (parameters) from *what is constant* (the procedure itself).
                Values reference parameters with {{mustache}} syntax.
 4. SAFE      — steps that commit state (post/submit/pay) carry
                `requires_approval: true`; the executor hard-pauses there
                until a human approves via the API. Fintech-grade default.
 5. TESTABLE  — the spec is deterministic data: snapshot tests, JSON-schema
                validation, dry-runs.

A step's `value` may reference:
  {{param_key}}     — a run-time input parameter
  {{extract.key}}   — the output of a prior `extract` step (data read from a
                      page during the run, e.g. scraped off the invoice page)
"""
from __future__ import annotations

import re
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from .trace import TargetInfo

PARAM_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    EXTRACT = "extract"     # read text from an element into extract.<key>
    ASSERT_TEXT = "assert_text"  # validation checkpoint


class RiskLevel(str, Enum):
    READ = "read"           # navigation, extraction — reversible
    WRITE = "write"         # typing into a form — reversible until submit
    COMMIT = "commit"       # posts/submits/pays — irreversible, gate it


class WorkflowParameter(BaseModel):
    key: str
    description: str = ""
    example: str | None = None
    required: bool = True


class WorkflowStep(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    intent: str = Field(description="One human-readable sentence: what & why")
    action: ActionType
    target: TargetInfo | None = None   # None for NAVIGATE
    value: str | None = None           # literal, {{param}}, or {{extract.k}}
    url: str | None = None             # NAVIGATE only; may contain {{param}}
    extract_key: str | None = None     # EXTRACT only: name of the output
    risk: RiskLevel = RiskLevel.READ
    requires_approval: bool = False

    def referenced_params(self) -> set[str]:
        refs: set[str] = set()
        for text in (self.value, self.url):
            if text:
                refs.update(PARAM_RE.findall(text))
        return refs


class WorkflowSpec(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    description: str = ""
    version: int = 1
    source_trace_ids: list[str] = Field(default_factory=list)
    parameters: list[WorkflowParameter] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)

    # ---- integrity helpers -------------------------------------------------

    def validate_references(self) -> list[str]:
        """Return a list of problems (empty == spec is internally consistent).

        Catches the two bugs that silently break replays: a step referencing
        a parameter that was never declared, and a step referencing an
        extract output that no earlier step produces.
        """
        problems: list[str] = []
        declared = {p.key for p in self.parameters}
        extracts_so_far: set[str] = set()
        for i, step in enumerate(self.steps):
            for ref in step.referenced_params():
                if ref.startswith("extract."):
                    key = ref.split(".", 1)[1]
                    if key not in extracts_so_far:
                        problems.append(
                            f"step {i} ('{step.intent}') references "
                            f"{{{{{ref}}}}} before any extract produces it"
                        )
                elif ref not in declared:
                    problems.append(
                        f"step {i} ('{step.intent}') references undeclared "
                        f"parameter {{{{{ref}}}}}"
                    )
            if step.action == ActionType.EXTRACT and step.extract_key:
                extracts_so_far.add(step.extract_key)
            if step.risk == RiskLevel.COMMIT and not step.requires_approval:
                problems.append(
                    f"step {i} ('{step.intent}') is risk=commit but "
                    f"requires_approval is false"
                )
        return problems


def render_template(text: str, params: dict[str, str]) -> str:
    """Substitute {{refs}} in `text` from a flat params dict.

    `params` contains both run inputs ("invoice_id") and extract outputs
    ("extract.amount"). Unknown refs raise — better to fail loudly than to
    type a literal '{{amount}}' into an ERP field.
    """

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in params:
            raise KeyError(f"unresolved template reference: {{{{{key}}}}}")
        return params[key]

    return PARAM_RE.sub(_sub, text)
