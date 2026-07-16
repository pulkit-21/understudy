# Understudy

**Watch a person do a browser task once. Learn the procedure — not the clicks. Run it on new data, with a human approval gate before anything irreversible.**

Built for the "learn a user's process by watching them, then do it for them" problem statement, scoped to the workflow that finance-operations teams actually drown in: moving data between systems that don't talk to each other (an invoice portal → an ERP).

## The demo in one paragraph

A user demonstrates once: open the **Vendra** invoice portal, open invoice INV-1001, read its fields, switch to the **LedgerOne** ERP, enter the bill, click *Post bill*. Understudy records **semantic events** (roles, labels, test-ids — never pixel coordinates), induces a **human-readable, parameterized workflow spec**, and can then run that procedure on invoices it has never seen. Because *Post bill* commits state, the induced spec flags it `requires_approval` — every replay hard-pauses there until a human approves via the API, and every action lands in an audit log with actor identity (`agent` / `human`) and timestamp.

## Why this scoping

- **Semantic traces, not macros.** RPA-style click recording breaks the moment a page changes. Understudy captures each action as *role + accessible name + data-testid + CSS fallback*, and the executor resolves targets through that chain at replay time (`testid → role+name → css`), reporting when it "healed" via a fallback.
- **The learned artifact is legible and editable.** The workflow spec is plain JSON: every step carries a one-sentence `intent`, values reference `{{parameters}}` or `{{extract.*}}` outputs, and risky steps carry `requires_approval`. A finance reviewer can audit the procedure; the UI can render it as an editable list. Trust in the artifact *is* the product.
- **Deterministic first, LLM second.** The heuristic inducer does the load-bearing work *deterministically* — including **provenance**: it rewrites the click that opened one invoice into a parameterized navigate, and turns values that were read off a page and typed later into live `extract` steps (targeting the page's real testids, captured as `readable_fields`). The result needs only `invoice_id`; everything else is read live — with **no API key, in CI, exactly tested**. The LLM layer then does only **legibility** (reviewer-grade step intents, a phase-listing description), behind a hard structural invariant: it may never change an action, target, value, or approval gate, and any deviation falls back to the deterministic spec. Correctness never depends on the model.
- **Irreversible actions are gated by construction.** `risk: commit` without `requires_approval: true` fails spec validation. The executor's pause has no timeout bypass.

**Deliberately out of scope:** real third-party sites (auth, 2FA, CAPTCHA), credential handling, multi-site generalization, and a Chrome-extension recorder (the capture script is extension-portable, but store review doesn't fit the timeline; the Playwright demonstration browser is the primary recorder).

## Proof it works

- `tests/test_e2e.py` — a real headless Chromium learns from the INV-1001 demonstration and executes on **INV-1005** (unseen data), pausing at the gate, completing after approval, with the ERP row asserted field-for-field.
- `scripts/eval.py` — runs the learned workflow across **all 8 seeded invoices** and reports a success rate. Current: **8/8 (100%)**.

## Architecture

```
demonstration browser (Playwright + inject.js)      ← semantic event capture
        │  Trace (JSON)
        ▼
induction: heuristic baseline ──► LLM enrichment    ← intents, params, provenance
        │  WorkflowSpec (JSON, editable)
        ▼
executor: Runner ──► ActionSink                     ← approval gates, audit log
                     ├─ PlaywrightSink (self-healing locator chain)
                     └─ FakeSink (tests)
        │  RunEvents
        ▼
FastAPI: /api/traces /api/workflows /api/runs (+SSE) ─ React control panel
mock apps: /portal (Vendra)  /erp (LedgerOne)        ─ deterministic demo stage
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
python scripts/seed_demo.py                 # demo trace + induced workflow
uvicorn app.main:app --app-dir backend --reload
```

Open http://localhost:8000 — links to the portal, the ERP, and API docs.
Optional: `export ANTHROPIC_API_KEY=...` to enable LLM enrichment of induction.

```bash
pytest                    # 16 tests, including the browser e2e (~2s)
python scripts/eval.py    # success-rate harness across all invoices
docker build -t understudy . && docker run -p 8000:8000 understudy
```

## Repository map

```
backend/app/models/       Trace + WorkflowSpec (the IR — start reading here)
backend/app/recorder/     inject.js capture script + Playwright session
backend/app/induction/    heuristic baseline + LLM enrichment
backend/app/executor/     Runner, approval gates, PlaywrightSink, RunManager
backend/app/mockapps/     Vendra + LedgerOne (deterministic demo stage)
backend/app/api/          REST + SSE
tests/                    contract, induction, executor, e2e, API tests
scripts/                  seed_demo.py, eval.py
decisions.md              the judgment log — what I chose, rejected, and why
CLAUDE.md                 build state + remaining plan (for Claude Code)
```
