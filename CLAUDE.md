# CLAUDE.md — Understudy build guide

Context for Claude Code sessions. Read README.md first for the product story.

## What this is

5-day take-home for Zamp.ai (fintech AI-agents company; product "Pace" is a
"digital employee" for finance ops — AP, reconciliation, ERP posting, with
audit trails and human escalation). Understudy is problem #2: learn a browser
workflow by watching a demonstration, then automate it. The demo workflow —
invoice portal → ERP posting with an approval gate — is chosen to mirror
Zamp's own use cases. Evaluation criteria: problem framing, product thinking,
UX, code quality, meaningful tests, docs, setup ease, velocity, depth.

## Current state (Day 1 complete — do not regress these)

DONE and tested (16 tests green, all core paths):
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

### Day 2 — LLM induction quality + recording UX
1. Wire recording start/stop endpoints for LOCAL use (spawn RecordingSession
   headful; POST /api/recordings/start {name, start_url}, /stop → trace id).
2. Test enrich_with_llm against the seeded trace with a real key; iterate the
   prompt until it reliably produces: extract steps on the invoice detail
   page (targets exist: inv-number/inv-vendor/inv-date/inv-amount/inv-gl),
   parameterized navigate/click ("open invoice {{invoice_id}}" — rewrite the
   open-INV-1001 click into navigate to /portal/invoice/{{invoice_id}}), and
   a single `invoice_id` parameter. End state: a run needs ONLY invoice_id;
   all other values are extracted live (the provenance wow).
3. Add induction snapshot tests: assert structure/keys, not prose (temp 0).

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
