# decisions.md

A running log of the real calls made while building **Understudy**. Not a
changelog — a record of judgment under a 5-day clock. Each entry is: what I
chose, what I seriously considered instead, why I went the way I did (including
the tradeoff I accepted), and what I deliberately cut.

Newest decisions are appended at the bottom, so this reads top-to-bottom as the
build unfolded.

---

## D1 — Which of the three problems, and how narrowly to scope it

**Decision.** Took problem #1 ("learn a user's process by watching them, then do
it for them") and scoped it to a single, concrete workflow: moving invoice data
from a vendor portal into an ERP, with a human approval gate before the
irreversible posting step. I built the two systems as deterministic mock apps
("Vendra" portal, "LedgerOne" ERP) so the demo is self-contained and
reproducible.

**Alternatives considered.**
- *General-purpose "record any website" tool.* The honest version of this is an
  RPA product, and in 5 days it would be a shallow one.
- *A different demo domain* (e.g. filling a signup form, scraping a table). Less
  risk, but also less signal.

**Reasoning / tradeoff.** Zamp's product ("Pace") is a digital employee for
finance ops — AP, reconciliation, ERP posting, with audit trails and human
escalation. Choosing a finance portal→ERP workflow lets the same build
demonstrate the general capability *and* speak directly to the domain the
evaluator lives in. The tradeoff I accepted: by mocking both apps I don't prove
the recorder survives a hostile real-world site (auth, CAPTCHA, iframes). I'd
rather go deep on the *learning and replay* problem — the actual hard part —
than spend the budget fighting Cloudflare. Depth over breadth is explicitly what
the rubric rewards.

**Deliberately cut.** Real third-party sites, credential/2FA handling,
multi-site generalization. Listed as out-of-scope in the README rather than
half-built.

---

## D2 — Capture *semantic events*, not pixels or raw DOM paths

**Decision.** The recorder captures each user action as a **semantic event**:
element role + accessible name + `data-testid`, with a CSS selector only as a
last-resort fallback. It never records screen coordinates, and it computes the
accessible name the way a screen reader would (label/aria/text), walking
`composedPath()` so it also works through shadow DOM.

**Alternatives considered.**
- *Coordinate/pixel replay (classic RPA).* Trivial to record; breaks the instant
  a button moves 3px or the viewport changes.
- *Absolute DOM/XPath replay.* Survives repaints but not markup changes, and
  produces selectors no human can read or edit.
- *Vision/screenshot-driven agent* that re-derives the UI each run from pixels.
  Powerful and trendy, but non-deterministic, slow, expensive per step, and
  impossible to audit — the opposite of what a finance workflow needs.

**Reasoning / tradeoff.** The whole thesis is "learn the *procedure*, not the
clicks." A semantic event is the smallest unit that carries intent ("fill the
field labelled *Amount*") independent of layout. It's also the unit a human can
read in the induced spec and trust. Tradeoff: computing accessible names and
maintaining the locator chain is real engineering I had to get right, and some
interactions don't reduce cleanly to a labelled element.

**Deliberately cut.** `contenteditable` regions, drag-and-drop, native file
uploads, canvas. Documented as known gaps rather than faked.

---

## D3 — Playwright demonstration browser as the recorder, not a Chrome extension

**Decision.** The primary recorder is a headful Playwright browser that injects a
capture script (`inject.js`) into the page. The user demonstrates in that
window.

**Alternatives considered.**
- *Chrome extension (Web Store).* The "correct" long-term shape — it records in
  the user's own browser on real sites. But Web Store review takes days-to-weeks,
  which fits no 5-day timeline.
- *Unpacked/dev-mode extension.* Skips review, but forces every evaluator to
  side-load it and toggle developer mode — friction on the "setup experience"
  criterion, and it still can't be part of a hosted demo.

**Reasoning / tradeoff.** Playwright gives me a headful record path locally *and*
a headless replay path on a server from the same primitives, with zero install
friction for the evaluator. I deliberately kept `inject.js` framework-agnostic
and extension-portable, so the extension is a documented next step rather than a
throwaway. Tradeoff: the local recorder needs a display, so on the deployed
instance recording happens via a script/bookmarklet injected into the mock apps
(Day 4) rather than the Playwright window.

**Deliberately cut.** The extension itself. Called out in "what I'd build next."

---

## D4 — The learned artifact is a legible, editable JSON spec (an IR), not opaque replay

**Decision.** Induction produces a **WorkflowSpec**: plain JSON where every step
carries a one-sentence natural-language `intent`, values reference
`{{parameters}}` or `{{extract.*}}` outputs, and risky steps carry
`requires_approval` and a `risk` level. It's the centerpiece of the system.

**Alternatives considered.**
- *Opaque replayable log* (just re-fire the recorded events). Simplest, but
  nobody can inspect, edit, or trust it, and it can't be parameterized.
- *Code generation* — emit a Playwright script. Editable by engineers, but not by
  the finance reviewer who actually owns the process, and it smuggles control
  flow into code where safety invariants can't be checked structurally.

**Reasoning / tradeoff.** In a finance context, *trust in the artifact is the
product*. A reviewer has to be able to read the procedure, see where the gate is,
and edit an intent or a parameter without touching code. A declarative IR also
lets me *enforce* safety by validation (see D6) — something you can't do to
arbitrary generated code. Tradeoff: an IR only expresses what I model; complex
branching/looping isn't representable yet.

**Deliberately cut.** Conditionals/loops in the IR, and codegen. The spec is
linear-with-extraction for now.

---

## D5 — Two-layer induction: deterministic heuristic first, LLM enrichment second

**Decision.** A deterministic heuristic inducer produces a structurally-valid
spec offline (no network, no key). An LLM enrichment layer then improves step
naming, parameterization, and — its unique contribution — **provenance**
(linking typed values back to the page they were read from). Enrichment runs at
temperature 0 and **falls back to the heuristic spec on any failure**.

**Alternatives considered.**
- *Pure-LLM induction* — hand the raw trace to the model, get a spec back. Less
  code, but non-reproducible, untestable in CI, and it makes the core capability
  fail whenever the API is down or the key is missing.
- *Pure heuristic* — fully deterministic, but produces robotic intents and can't
  infer that a value the user typed was actually *read* from an earlier page.

**Reasoning / tradeoff.** The happy path must be deterministic so it's testable,
reproducible, and auditable — the LLM is an enhancement, never a dependency. The
heuristic guarantees a working spec exists; the LLM makes it *smart*. Tradeoff:
maintaining two inducers is more code than one, and I have to keep the LLM's
output on the same schema.

**Deliberately cut.** Any design where the demo breaks without an API key.

---

## D6 — Approval gates are enforced by construction, not by convention

**Decision.** A step with `risk: commit` and no `requires_approval: true` **fails
spec validation** — you cannot save such a workflow. At run time the executor
hard-pauses at gated steps on an `asyncio.Event` with **no timeout bypass**, and
the LLM enrichment layer is forbidden (as a hard invariant) from ever removing a
gate. Every action is written to an audit log with actor identity (`agent` vs
`human`) and a timestamp.

**Alternatives considered.**
- *Soft warning* ("this step is risky") that a run can proceed past. Easy to
  ignore, and one config flag away from a fully-autonomous money mover.
- *Configurable auto-approve / timeout-then-proceed.* Convenient, and exactly the
  footgun that turns "human in the loop" into theater.

**Reasoning / tradeoff.** For irreversible finance actions the human gate is a
safety *invariant*, not a feature toggle. Encoding it in validation means it
can't be forgotten, and encoding "enrichment may never remove a gate" means the
smart layer can't quietly weaken the safe layer. Tradeoff: less flexibility (you
can't build a fully-autonomous flow), which is the point.

**Deliberately cut.** Any auto-approve path. Unresolved `{{refs}}` also *fail the
run* rather than typing a literal — a value we can't trace is never silently sent.

---

## D7 — Self-healing locator chain, reported — with LLM fallback left as a stretch

**Decision.** At replay the executor resolves each target through a chain:
`data-testid → role + accessible name → CSS`. When it succeeds via a fallback it
records that it "healed," so drift is observable rather than silent.

**Alternatives considered.**
- *Single strategy* (testid only, or CSS only). Brittle; one markup change and
  the run dies.
- *LLM locator fallback* — when all three strategies miss, ask a model to find
  the element from the page + the step's intent. Powerful, but it makes the happy
  path model-dependent and non-deterministic if over-used.

**Reasoning / tradeoff.** Graceful, *observable* degradation is what makes a
replay trustworthy — you can see when the page moved under it. I wired the
"healed" reporting so an LLM fallback can slot in behind it later without
changing the happy path. Tradeoff: the deterministic chain won't survive a
wholesale redesign of the target page; the LLM fallback that would is deferred.

**Deliberately cut (stretch).** LLM locator fallback. The reporting hook is in
place for it.

---

## D8 — Provenance / live extraction is the hard sub-problem I chose to own

**Decision.** The system links values the user *typed* into the ERP back to the
page fields they were *read from* in the portal, and rewrites them as live
`extract` steps. End state: replaying the workflow needs **only an
`invoice_id`** — vendor, date, amount, and GL code are all extracted live from
the invoice page at run time, not stored as parameters.

**Alternatives considered.**
- *Parameterize everything* — treat every typed value as an input the caller must
  supply. Simpler, but that's a form-filler with variables, not something that
  *learned a process*. It also can't scale to "run this on 500 invoices."

**Reasoning / tradeoff.** This is the difference between a parameterized macro and
a system that understood the workflow: it knows the amount in the ERP *comes
from* the invoice, so on new data it re-reads it rather than being told. This is
the depth the rubric asks for — the part most people would skip. Tradeoff: it
leans on the LLM enrichment layer to establish provenance reliably (Day 2 work),
guarded by the heuristic fallback.

**Deliberately cut.** Cross-page provenance for values that aren't visible on a
single captured page. Scoped to fields present in a page-text snapshot.

---

## D9 — Filesystem JSON for traces/specs/runs, not a database

**Decision.** Traces, workflow specs, and run logs are JSON files under
`UNDERSTUDY_DATA` (default `./data`).

**Alternatives considered.**
- *SQLite / Postgres.* Proper queries, concurrency, migrations.

**Reasoning / tradeoff.** For a 5-day build the artifacts *are* the thing you
reason about — inspectable, diffable, and directly usable as test fixtures.
Files let an evaluator `cat` a learned workflow and see exactly what was induced.
Tradeoff: no concurrent-write safety and no rich query; fine at demo scale,
documented as the boundary where a DB earns its place.

**Deliberately cut.** A datastore, until there's a real multi-user story.

---

## D10 — In-memory ERP state and an unauthenticated reset hook

**Decision.** The LedgerOne ERP holds posted bills in memory and exposes an
unauthenticated `/erp/_reset`. State resets on redeploy.

**Alternatives considered.** A persistent bills store.

**Reasoning / tradeoff.** For a demo, a clean, resettable stage is a *feature* —
every eval run starts from a known state, and `_reset` makes tests hermetic.
Because the ERP is a sandbox mock with no real data, leaving `_reset`
unauthenticated is a deliberate, stated tradeoff, not an oversight.

**Deliberately cut.** Auth and persistence on the mock apps.

---

## D11 — One Chromium per run; no pooling

**Decision.** The run manager launches a fresh Chromium per run.

**Alternatives considered.** A browser/context pool reused across runs.

**Reasoning / tradeoff.** Per-run isolation is correct and simple at demo scale;
pooling is a real optimization with real complexity (lifecycle, cleanup on
crash, cross-run bleed) that a 5-day demo doesn't need. Tradeoff: throughput and
cold-start cost under load. Documented as an explicit scaling boundary rather
than prematurely optimized.

**Deliberately cut.** Browser pooling.

---

## D12 — Single service: FastAPI serves the built React app same-origin

**Decision.** The backend (FastAPI) and the frontend (Vite + React) ship as one
service — FastAPI serves the built assets via `StaticFiles`.

**Alternatives considered.** Separate frontend deploy (e.g. static host) talking
to the API cross-origin.

**Reasoning / tradeoff.** One service is one deploy, one URL, no CORS dance —
strictly better on the "setup experience" and "a stranger can run it in one
shot" criteria. Tradeoff: the frontend can't scale independently of the API,
which is irrelevant at this scale.

**Deliberately cut.** Independent frontend hosting/CDN.

---

## D13 — Provenance is deterministic (in the heuristic), not the LLM's job

**Decision.** Turning a value that was *read* off a page and *typed* later into a
live `extract` step — the "invoice_id is the only input" capability — is done
**deterministically in the heuristic inducer** by exact-matching typed values
against the page's captured fields. It runs with no API key and in CI.

**Alternatives considered.**
- *LLM-owned provenance* (the original plan, [[decisions]] D8): hand the trace to
  the model and let it infer which values were read where. Fewer moving parts in
  the heuristic, but it makes the flagship capability non-reproducible, untestable
  in CI, and broken whenever the key is absent or the model has an off day.

**Reasoning / tradeoff.** The whole thesis (D5) is deterministic-first because
finance work must be reproducible and auditable. It was incoherent to then make
the *most important* transformation LLM-dependent. Exact-match provenance is
simple, exact, and snapshot-testable; the eval now proves it live across all 8
invoices (reading each one's real vendor/date/amount/GL, not fed values). The
tradeoff: exact matching misses values that are reformatted between the source
page and the ERP (e.g. `4,820.00` vs `4820.00`) — those fall back to being a
parameter. That's the seam where the LLM earns its place (see D15).

**Deliberately cut.** Fuzzy/semantic provenance in the deterministic layer —
left as the LLM's documented extension.

**Supersedes** the framing in D8 that provenance was "the LLM's unique
contribution." The hard sub-problem is still owned — just deterministically.

---

## D14 — The recorder captures structured `readable_fields`, so extract targets are real

**Decision.** On every navigation the recorder snapshots not just page text but a
structured list of **readable fields** — each labelled, testid'd value visible on
the page. Extract steps target the *actual* testid from that snapshot.

**Alternatives considered.**
- *page_text only* + let induction guess element selectors for extraction. But the
  invoice page's values live in a `<dl>` with no form roles, so there's nothing to
  reliably locate by — the inducer would have to *invent* a selector, which every
  layer here is forbidden from doing.
- *Have the user click each value during the demo* so it's captured as a normal
  target. Unnatural — people read pages, they don't click every field.

**Reasoning / tradeoff.** This is what makes deterministic provenance *honest*:
the extract step points at an element the recorder genuinely saw, so the executor
can locate it. I verified parity by running the real `inject.js` against the live
mock app — a demonstration on INV-1005 produces exactly the fields the inducer
needs. Tradeoff: more captured per page; capped and de-duped.

---

## D15 — The LLM is narrowed to legibility, behind a hard structural invariant

**Decision.** Now that correctness is deterministic, the LLM enrichment layer may
change *only* human-readable text: the workflow `name`, its `description`, and each
step's `intent`. A structural invariant (`validate_enrichment`) rejects any
enriched spec whose actions, targets, values, extract keys, risk levels, approval
gates, or parameter set differ from the deterministic draft — on any violation we
ship the draft. The stochastic layer can make the workflow nicer to read; it can
never make it wrong.

**Alternatives considered.**
- *Let the LLM restructure freely* (rewrite steps, re-parameterize). More
  "powerful", but it puts the model on the correctness path, which is exactly what
  D5/D13 argue against — and it's far harder to test.

**Reasoning / tradeoff.** Keeping the LLM off the correctness path makes the whole
system trustworthy *and* testable: the invariant is a pure function unit-tested
offline (gate removal, target changes, value changes, step add/remove all
rejected), while the live call is exercised manually with a key. Tradeoff: the LLM
can't *fix* a bad deterministic draft — but if the draft is wrong, the fix belongs
in the deterministic layer where it's reproducible, not in a prompt.

**Deliberately cut.** LLM-driven restructuring and re-parameterization.

---

## D16 — Default induction model: `claude-opus-4-8`

**Decision.** The enrichment layer defaults to `claude-opus-4-8` (overridable via
`UNDERSTUDY_MODEL`), temperature unset.

**Alternatives considered.** The prior `claude-sonnet-4-6` default; a cheaper
Haiku tier for a text-only task.

**Reasoning / tradeoff.** This is an AI-agents showcase for an AI-agents company;
defaulting to the latest, most capable model is the right signal, and enrichment
is infrequent (once per induction), so cost is a non-issue. The task is
low-volume, not latency-sensitive. (Opus 4.8 rejects `temperature`, so it's
omitted — the structural invariant, not sampling, is what makes output safe.)

**Deliberately cut.** A cost-tuned model tier — irrelevant at induction volume.

---

## D17 — Request bodies are module-scope Pydantic models (a latent API bug, fixed)

**Decision.** All request-body models (`InduceBody`, `RunBody`,
`StartRecordingBody`) live at module scope, not inside the router factory.

**What happened.** They were originally defined *inside* `build_router`. FastAPI +
pydantic v2 cannot build a schema for a function-local model (its qualname carries
`<locals>`), so it silently demoted each body parameter to a *query* parameter —
making every body-taking endpoint (`/induce`, `/runs`, and the new recording
routes) return `422 "field required"`. No test caught it because the e2e drives the
`Runner` directly and nothing had exercised those endpoints over HTTP yet — it
would have surfaced only when the Day-3 frontend tried to call them.

**Reasoning.** Found it by writing API-level tests through the real HTTP layer
before building the UI on top. Added those tests so it can't regress. Lesson
banked: test the transport boundary, not just the logic beneath it.

---

## D18 — Local recording endpoints (headful), hosted recording via injected script

**Decision.** `POST /api/recordings/start` spawns the headful Playwright
demonstration browser and `POST /api/recordings/{id}/stop` returns the saved
trace — the local record→learn→run loop over HTTP. On a display-less host the
start endpoint fails with a clear message pointing at the hosted path: the same
`inject.js` served into the mock apps, POSTing the trace to `/api/traces`.

**Alternatives considered.** Only the programmatic recorder (no HTTP surface) —
but then the UI can't start a recording. A WebSocket channel for live events —
unnecessary; the trace is delivered whole on stop.

**Reasoning / tradeoff.** Two honest paths for two environments, sharing one
capture script and one trace format. Tradeoff: headful recording needs a display,
so it's a local-only convenience; the endpoint says so rather than pretending.

**Deliberately cut.** Live event streaming during recording; multi-user recording
sessions.

---

## D19 — Run/approve endpoints are `async` (a second latent event-loop bug, fixed)

**Decision.** `POST /workflows/{id}/runs`, `/runs/{id}/approve`, and `/reject`
are `async def`.

**What happened.** They were sync `def`, so FastAPI ran them in a threadpool.
`RunManager.start_run` calls `asyncio.create_task`, which needs a running loop —
from a threadpool thread there is none, so starting a run raised
`RuntimeError: no running event loop` and nothing executed. The approve/reject
path had a subtler version of the same disease: `asyncio.Event.set()` called from
a threadpool thread doesn't reliably wake a waiter blocked on the loop, so even
if a run had started, approval might never have resumed it.

**Reasoning.** Like D17, this only surfaced when I drove the endpoints for real —
here by running the full UI loop headless (Playwright against the built SPA)
rather than trusting a green typecheck. Making the endpoints async puts them on
the loop thread, so both `create_task` and `Event.set()` behave. Banked lesson:
endpoints that touch asyncio primitives must be async, and "it compiles / renders"
is not "it works" — drive the actual flow.

---

## D20 — React SPA, served same-origin by FastAPI; the spec is the UI

**Decision.** A Vite + React + TypeScript control panel (`frontend/`), built to
static assets and served by FastAPI (D12). Three views: a workflows/demonstrations
list, an **editable workflow detail** page, and a **run** page with a live SSE
audit log and the approval gate. Plain hand-written CSS, no UI framework.

**Alternatives considered.**
- *Server-rendered templates* (extend the Jinja mock-app stack). Faster to stand
  up, but the run view needs live streaming and inline editing — that's a
  client-state problem, and SSR would fight it.
- *A component library* (MUI/Chakra/Tailwind). Saves styling time but adds bulk
  and a generic look; the surface here is small enough that ~250 lines of CSS
  gives a more considered, product-specific feel.

**Reasoning / tradeoff.** The product thesis is "the learned artifact is legible
and trustworthy," so the UI's job is to make the spec and the audit trail *read*
well: every step shows its action, risk, real target testid, and whether each
value is read-live (`↳ read: vendor`) or a run input (`input: invoice_id`); the
commit step is visually gated with a toggle; the run log shows actor (agent vs
human) + timestamp per line. TypeScript + a typed API client keep the front and
back ends honest about the same shapes. Tradeoff: a build step and a second
toolchain — paid down by same-origin serving so it's still one deploy.

**Deliberately cut.** Auth, optimistic caching/react-query, a component library,
dark mode. Not needed at this surface.

---

## D21 — Real persistence: SQLAlchemy + Alembic, document-per-row, SQLite→Postgres by env

**Decision.** Replace the JSON/in-memory stores with a proper database:
SQLAlchemy 2.0 ORM, Alembic migrations (run on boot), and a repository layer
that is the only code touching the ORM. Each aggregate (trace, workflow, run)
is one row storing the domain Pydantic model as a JSON `payload` **plus**
extracted, indexed columns (name, status, workflow_id, timestamps) for the
queries the UI runs. `DATABASE_URL` unset → SQLite under the data dir (zero-ops
demo default); set to a `postgres://` URL → Postgres. Runs now persist at start
and at terminal state, so there's a durable run history.

**Alternatives considered.**
- *Keep JSON files* (the Day-1 choice). Genuinely fine for the artifacts —
  they're document-shaped and inspectable — but reads as a prototype next to the
  reference solutions, and gave no run history, no concurrent-safe writes, no
  queryable metadata. The reference bar is a real DB; this is the gap-closer.
- *Full normalization* (tables for steps, events, params with FKs). Correct when
  data is relational; wrong here — a spec is one nested tree, a run carries its
  own embedded event log. Normalizing them would be mapping code for no query we
  actually run, and would lose the verbatim round-trip.
- *Postgres-only.* Matches the references exactly but adds a managed-DB
  dependency to a demo that should run in one command. SQLite-default +
  Postgres-by-env keeps `git clone && run` friction-free while proving the
  code is backend-agnostic (the repository layer is the seam).

**Reasoning / tradeoff.** Document-per-row is the honest model for these
aggregates: it keeps the "inspectable JSON" property the file store gave us
(the payload is the exact domain model) while adding a real schema, migrations,
indexed listing, and durability. Verified by restarting the server mid-history
and reading a completed run — 33 events + live extracts — back from disk.
Tradeoff accepted: JSON columns aren't as queryable as normalized fields, but
the extracted columns cover every list/filter the product needs.

**What I deliberately cut.** Per-field normalization, an async DB driver
(sync sessions are simple and fine at demo scale; documented as a scaling
boundary), and connection pooling tuning.

**Bug found while doing it.** The seed script imported the demo trace from
`tests/conftest.py`, which now sets `DATABASE_URL` to a temp DB on import — so
migrations ran against the temp DB while the repo wrote to the real one
("no such table"). Fixed by moving the canonical demo trace into `app/seed.py`
so runtime code never imports test modules. Lesson banked: test setup leaking
into a runtime import path is a real hazard.
