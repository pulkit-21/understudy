# CLAUDE.md — Understudy build guide

Context for Claude Code sessions. Read README.md first for the product story.

> **Status (current):** Days 1–5 complete, plus a production-hardening pass.
> Foundation: React control panel, auth + multi-tenancy, persistence
> (SQLAlchemy + Alembic, SQLite→Postgres), CI + ruff + mypy, robustness suite
> (self-healing selectors, safe failure, concurrency, SSE replay), in-browser
> recorder + rrweb session replay, Docker/`render.yaml` deploy with seed-on-boot.
> Hardening pass (D40–D45): central `pydantic-settings` config; conversational
> agent split onto **claude-sonnet-5** (induction stays on Opus); enriched mock
> apps (invoice PO/tax/due/status/line-items + filters, LedgerOne payment
> lifecycle); a **third seeded workflow** (gated bill payment); **⌘K command
> palette** + a11y pass; backend test hardening (coverage 80%→85%, a real
> `_build_cards` bug caught) and an end-to-end API-key delivery fix.
> **102 tests green; eval 8/8 + safe-fail.** Full decision log in
> `decisions.md` (D1–D45). The section below is the original Day-1 handoff.

## What this is

5-day take-home for Zamp.ai (fintech AI-agents company; product "Pace" is a
"digital employee" for finance ops — AP, reconciliation, ERP posting, with
audit trails and human escalation). Understudy is problem #2: learn a browser
workflow by watching a demonstration, then automate it. The demo workflow —
invoice portal → ERP posting with an approval gate — is chosen to mirror
Zamp's own use cases. Evaluation criteria: problem framing, product thinking,
UX, code quality, meaningful tests, docs, setup ease, velocity, depth.

## Current state (Days 1–2 complete — do not regress these)

### Day 2 additions (31 tests green; deterministic invoice_id-only)
- **Deterministic provenance.** The heuristic inducer now (a) rewrites a click
  that opens a run-varying URL (`open-INV-1001`) into a parameterized navigate
  (`/portal/invoice/{{invoice_id}}`), and (b) turns values read off a page and
  typed later into `extract` steps targeting the page's REAL testids. A run
  needs ONLY `invoice_id`; vendor/date/amount/GL are read live. No key, works in
  CI. (decisions.md D13.)
- **`readable_fields`** on navigate events (trace model + inject.js + fixture):
  structured provenance source, so extract targets are never invented. Verified
  real inject.js against the live mock app. (D14.)
- **LLM narrowed to legibility.** enrich_with_llm may change only name/
  description/intent; `validate_enrichment` (pure, unit-tested) rejects any
  structural change and falls back to the deterministic draft. Model default is
  now `claude-opus-4-8`. (D15, D16.)
- **API body bug fixed.** Request models were function-local → FastAPI demoted
  bodies to query params → every body endpoint 422'd. Hoisted to module scope;
  added HTTP-layer tests. (D17.)
- **Recording endpoints.** POST /api/recordings/start (headful, local) + /stop
  → saved trace; hosted path still via inject.js → /api/traces. (D18.)
- eval + e2e now run invoice_id-only (prove live extraction); eval also checks
  the extracted vendor. Still 8/8.

### Day 1 (tested, all core paths):
- Deterministic mock apps: Vendra portal (/portal) + LedgerOne ERP (/erp),
  stable data-testids, seeded data, /erp/_reset hook. Contract-tested.
- Trace model (semantic events) + inject.js recorder script (accessible-name
  computation, composedPath for shadow DOM, input collapsing to FILL on
  change, password fields never recorded, page_text snapshots on navigate
  for provenance).
- Playwright demonstration-browser recorder (RecordingSession) — headful,
  local use; traces persist as JSON (TraceStore).
- WorkflowSpec IR: per-step natural-language intent, {{param}} and
  {{extract.*}} templating, risk levels, requires_approval, and
  validate_references() (catches undeclared refs, extract-before-produce,
  and commit-without-gate).
- Heuristic induction (offline, deterministic): parameterizes dynamic values,
  flags commit submits for approval, keeps spontaneous navigations
  (regression-tested — dropping them stranded replays).
- LLM enrichment layer (anthropic sdk, temp 0): provenance→extract steps,
  intent rewriting; hard invariants enforced (never remove a gate, never
  invent selectors); falls back to heuristic draft on any failure.
- Executor: Runner walks spec, resolves templates, HARD-pauses at gated steps
  (asyncio.Event, no timeout bypass), audit log with actor identity;
  ActionSink boundary → PlaywrightSink (self-healing testid→role+name→css,
  reports "healed" hops) and FakeSink for tests.
- RunManager + full REST API (traces, induce, workflows CRUD w/ version bump
  + validation on PUT, runs, approve/reject, SSE event stream w/ history
  replay + keepalive).
- e2e test: real Chromium, demo on INV-1001 → run on INV-1005, gate held,
  ERP row asserted. Eval harness: 8/8 invoices pass.
- Dockerfile (mcr.microsoft.com/playwright/python base), seed script.

## Conventions

- Python 3.11+, pydantic v2, async throughout the executor/recorder.
- Data artifacts (traces, specs, run logs) are JSON files under
  UNDERSTUDY_DATA (default ./data) — inspectable, diffable, fixture-able.
- Every risky invariant gets a test. FakeSink for executor logic; real
  Chromium only in tests marked e2e.
- Never weaken: gates are non-bypassable; enrichment may never remove one;
  unresolved {{refs}} fail the run rather than typing literals.

## Remaining plan

### Day 2 — DONE (see decisions.md D13–D18)
Provenance made deterministic (invoice_id-only, in CI), readable_fields capture,
LLM narrowed to legibility with a structural invariant, model → opus-4-8, latent
API body bug fixed, recording endpoints wired, snapshot/invariant/API tests
added. 31 tests green; eval 8/8 with live extraction.

### Day 3 — React control panel (frontend/)
Vite + React. Pages: Traces (list, induce button), Workflow detail (editable
step list — rename intent, toggle requires_approval, edit params; PUT back;
surface 422 validation problems), Run view (params form, live SSE audit log,
screenshot strip, big Approve/Reject when awaiting_approval). Deploy note:
serve built assets from FastAPI (StaticFiles) to keep one service.
UI copy: buttons say what they do ("Post bill", "Approve step"); audit log
rows show actor + timestamp. Keep visual design quiet and product-like; the
star of the UI is the legible workflow spec.

### Day 4 — deployed recording + live view + hardening
1. Deployed recording story (no display on server): serve inject.js as a
   <script> tag injected into the mock apps when ?record=1 (or a small
   bookmarklet), buffering events client-side and POSTing the trace to
   /api/traces on "stop". This gives evaluators record→learn→run entirely
   in the hosted demo. (The Playwright recorder remains the local path.)
2. Screenshot streaming: on_step hooks already exist conceptually — have
   Runner call sink.screenshot() after each step, push base64 over the SSE
   stream (new event kind "frame").
3. Railway deploy: Dockerfile ready; ≥1–2GB RAM; set UNDERSTUDY_BASE_URL to
   the public URL; run seed on boot; /healthz for the platform. Warm before
   demoing. Frontend can stay same-origin (StaticFiles) — simplest.

### Day 5 — polish, docs, screencast
- README: add deployed URL, 2–3 min Loom, architecture diagram image,
  "what I'd build next" (multi-trace diffing to find parameters, LLM locator
  fallback when all three strategies miss, Chrome-extension recorder —
  unpacked only, store review doesn't fit any short timeline).
- Run eval.py fresh; paste the table into README.
- Failure-mode pass: dead browser, SSE reconnect, concurrent runs.

## Sharp edges / decisions already made

- Executor is deterministic-first; LLM locator fallback is a STRETCH, wired
  behind the existing "healed" reporting. Do not make the happy path
  LLM-dependent — reproducibility and auditability are the point.
- RunManager launches one Chromium per run: acceptable for demo scale;
  document as a scaling boundary, don't build pooling now.
- ERP state is in-memory: resets on redeploy — a feature for a demo. The
  _reset endpoint is intentionally unauthenticated in the sandbox; say so.
- Recorder ignores clicks on inputs (noise); FILL on change carries intent.
  Known gap: contenteditable, drag-drop, file uploads — out of scope, listed.
- If deploying fights back >½ day: local backend + deployed frontend +
  screencast, stated plainly in the README.
