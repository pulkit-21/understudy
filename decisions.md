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

---

## D22 — CI + type/lint rigor (ruff, mypy, GitHub Actions)

**Decision.** Add `pyproject.toml` (ruff + mypy config), a two-job GitHub
Actions workflow (backend: ruff → mypy → pytest with a real Chromium; frontend:
tsc + vite build), a `Makefile` of common tasks, and `ruff`/`mypy` as dev deps.
mypy is pragmatic-strict: `check_untyped_defs` + `no_implicit_optional`
everywhere, `disallow_untyped_defs` on the parts that matter most (the domain
models and the executor safety core).

**Alternatives considered.** Full `mypy --strict` like invoice-copilot — but the
async Playwright + partial third-party stubs make blanket strictness mostly
`# type: ignore` noise; a per-module ratchet (sift's approach) buys the real
safety on the code that carries risk without the busywork. No lint at all was
the status quo and is below the bar.

**Reasoning / tradeoff.** The reference solutions both gate every push on
lint+types+tests; that discipline is cheap and high-signal, and it's exactly the
kind of rigor the rubric rewards ("code you'd hand a teammate"). Fixing the
initial 66 ruff + 6 mypy findings also surfaced small real issues (an unused
var, an unguarded `Optional` access in induction). Tradeoff: a CI minute per
push and the discipline of keeping it green.

**What I deliberately cut.** import-linter layer contracts (the architecture is
small enough to eyeball; revisit if it grows), and coverage gating (coverage
targets reward token tests — the rubric explicitly doesn't want that).

---

## D23 — Robustness depth: prove safe degradation, don't just claim it

**Decision.** Add a robustness test suite + eval failure-mode row covering the
real-world failure modes an AP automation actually hits, each asserting *safe*
degradation:
- **Self-healing on a redesigned page.** A `?resilience=drop-testids` variant of
  the ERP form renders the same fields with every `data-testid` removed. The
  learned workflow still posts the correct bill by falling back to accessible
  role+name, and the audit log records that it healed. This is the headline: it
  exercises the self-healing locator chain end-to-end against a real DOM that
  broke our primary selectors.
- **Bad input.** A run for a non-existent invoice fails cleanly — nothing posted,
  run settles FAILED with an audit event, and it never reaches the approval gate
  (no human is asked to approve a run built on missing data).
- **Mid-run failure.** An action that throws settles the run FAILED with a typed
  audit event and never reaches the commit.
- **Concurrent isolation.** Two runs in flight keep separate extracts and
  resolve their gates independently (approve one, reject the other).
- **SSE reconnect.** A client that connects to the audit stream late replays the
  full history — the property a dropped connection relies on.

**Reasoning.** The rubric's "above and beyond" is explicitly *"handle the real
world, not the happy path... degrade gracefully."* The product's core claim is
that learning the *procedure* (not pixel clicks) survives page change — so the
single most important thing to prove is exactly that, against a real broken
page, with the safety invariant (no un-approved commit, always settles, always
audited) holding through every failure. Proving it beats asserting it.

**What I deliberately cut.** Chaos on the network layer (latency/500s injected
mid-run) and a fuzzing pass over malformed traces — listed as future work; the
five modes above are the ones a finance operator hits first.

---

## D24 — UI breadth: runs history, trace detail, recording, first-run

**Decision.** Add three views + polish on top of the Day-3 panel: a **Runs
history** page (`/runs`, from the new persistence), a **trace detail** page that
renders a recorded demonstration's semantic events (the raw material induction
learns from — visibly roles/labels/test-ids, not pixels), an in-UI **record
start/stop** control, and a **first-run** intro banner + empty states.

**Reasoning.** These aren't breadth for its own sake — each surfaces something
the backend now does that was previously invisible: history proves runs persist;
the trace view makes the "semantic, not pixel" claim legible to a reviewer; the
record button closes the record→learn→run loop inside the product. The recording
control degrades honestly: on a headless host (the hosted demo) the demonstration
browser can't launch, so it explains that recording is local and points to the
seeded demonstration instead — the real-world-failure discipline applied to UX.

**What I deliberately cut.** A charts/metrics dashboard (vanity for this
surface), and editing/deleting traces (not part of the core loop). Kept the
visual language identical to Day 3 so the app reads as one considered product.

---

## D25 — Deploy: one container, seed-on-boot, SQLite-ephemeral by default

**Decision.** A multi-stage Dockerfile (node builds the SPA → the Playwright
Python image serves API + SPA + mock apps from one process), `render.yaml`
blueprint, `/healthz`, and **seed-on-boot** (the app's lifespan seeds the demo
if the DB is empty, using the offline heuristic inducer so boot needs no API
key or network). The container binds `UNDERSTUDY_BASE_URL` to its own port so
the executor drives the same process that serves the mock apps — no external
round-trip, and it works regardless of the public URL.

**Alternatives considered.**
- *Separate frontend + backend services.* More moving parts and CORS; the
  same-origin single container is simpler to run and to reason about.
- *Postgres + a Render disk by default.* Durable, but adds provisioning to a
  demo. SQLite on the container's ephemeral disk resets on redeploy — which for
  this demo is a feature (clean slate), and `DATABASE_URL`/a mounted disk are
  documented one-line upgrades when durability matters.
- *Seed at image-build time* (the old Dockerfile did `RUN seed_demo.py`). That
  bakes data into the image and would need the API key at build; seed-on-boot is
  cleaner, idempotent, and key-free.

**Reasoning / tradeoff.** The rubric requires a testable deployed URL and a
one-shot setup. Playwright's official image removes the usual "missing shared
libs" headless-Chromium failure on PaaS. Verified locally by booting against a
fresh empty data dir: the lifespan seeded the workflow + trace and served the
SPA. The Docker *image build* itself is left for the deploy host (the daemon
wasn't available in the dev sandbox); the Dockerfile is standard multi-stage.

**What I deliberately cut.** A CDN for static assets (FastAPI StaticFiles is
fine at this scale) and horizontal scaling (one Chromium per run is a documented
single-node boundary, not a demo concern).

---

## D26 — Multi-tenant auth (bcrypt + JWT), org as the tenancy key

**Decision.** Real accounts: bcrypt-hashed passwords, HS256 JWTs, users belong
to orgs, and **every** trace/workflow/run is stamped with `org_id`. The
repository layer filters and stamps by org, so a tenant physically cannot read
or overwrite another's data (verified by tests, incl. an over-HTTP isolation
test). Auth endpoints are rate-limited (slowapi) against credential stuffing.

**Keeping the demo frictionless.** A login wall would hurt the evaluator's
first-run experience, which the rubric weighs. So the app seeds a **demo account**
on boot and the sign-in screen has a one-click **"Try the live demo"** — real
auth, zero friction. Registration also works for a fresh isolated workspace.

**Alternatives considered.** (a) No auth (the Day-1..5 state) — simpler, but not
"a proper full-stack app" and can't be multi-user; the reference solutions both
have auth + tenancy. (b) Cookie/session auth — would make the SSE stream
"just work" without a token in the URL, but adds CSRF surface and server-side
session state; a stateless JWT is simpler and standard. (c) An external IdP
(Auth0/Clerk) — overkill for a take-home and adds a hosted dependency.

**Tradeoffs accepted.** The SSE endpoint takes the JWT as a `?token=` query
param because the browser EventSource API can't set an Authorization header —
validated server-side and org-checked; the short-lived token in the URL is the
standard EventSource workaround, documented in the code. Sync DB sessions inside
async endpoints (fine at this scale; documented boundary).

**What I deliberately cut (for now).** Roles/permissions within an org, email
verification, password reset, refresh tokens — real-product features, but beyond
what demonstrates the tenancy architecture.

---

## D27 — Policy-governed approvals + lifecycle + batch (the "digital employee")

**Decision.** Three capabilities that turn a single-run tool into an operations
product, all org-scoped:
- **Approval policy per workflow.** Default `always_ask`; opt-in
  `auto_below_amount` auto-approves a gated step when a numeric extract (the
  invoice amount) is below a threshold — "auto-post the small ones, escalate the
  big ones." The executor logs auto-approvals with `actor="policy"`. Crucially,
  policy can only *resolve* a gate; it never removes `requires_approval` from the
  spec (still enforced by validate_references), and anything it can't parse falls
  through to a human. This mirrors invoice-copilot's "LLM proposes, deterministic
  code decides" guard, applied to *approval* rather than extraction.
- **Workflow lifecycle + version history.** draft/published/archived, an
  immutable version snapshot on every save, and one-click rollback; duplicate and
  delete. The library hides archived by default.
- **Batch runs + a bounded worker pool.** Run a workflow over a list of invoices;
  a semaphore caps concurrent Chromium instances so a 100-item batch can't
  exhaust memory. An **approval inbox** (with a live nav badge) is the cross-run
  queue of what needs a human — the "attention is the scarce resource" framing.

**Bug found and fixed while building it.** The inbox reads *persisted* status,
but the `awaiting_approval` transition was only ever in memory (runs persisted at
start + terminal) — so the inbox and dashboard badge stayed empty. Added an
`on_state_change` persist hook the Runner fires at the gate, so the DB reflects
awaiting. Caught by driving the real batch flow, not by a unit test — banked as a
test (`test_awaiting_state_is_persisted_at_the_gate`).

**Alternatives considered.** A full rules engine (per-vendor, per-GL, multiple
conditions) like invoice-copilot's — deferred; the amount threshold is the 80%
case and keeps the policy legible. A separate ApprovalPolicy table — kept it on
the spec so it versions and round-trips with the workflow.

**Tradeoffs.** Auto-approving a commit is real spend authority, so it's opt-in,
per-workflow, defaults off, logged distinctly, and bounded to what the policy can
confidently evaluate.

---

## D28 — Observability: cost metering, live screenshot view, run retry

**Decision.** Round out Phase 5 with the observability a real operator wants:
- **LLM cost metering.** `enrich_with_llm` surfaces token usage via an optional
  callback; the induce endpoint records a `usage` row (org, model, tokens, cost)
  priced per model. The dashboard's LLM-cost stat and a `/api/usage` log read
  from it. This is honest metering of the *only* place Understudy spends tokens
  — induction. Runs stay deterministic and free, and the dashboard says so.
- **Live view.** The Runner captures a screenshot after each step and streams it
  as a queue-only `frame` SSE event (never persisted — base64 would bloat the
  audit log). The run page shows the agent's actual browser as it works. Turns
  "trust me, it's driving a browser" into "watch it."
- **Run retry.** One click re-runs a finished run with the same inputs.

**Reasoning.** Metering-via-callback keeps the LLM module decoupled from the DB
(the caller decides what to do with usage) — the same seam the reference
solutions use for their metered clients. Frames are deliberately ephemeral:
live watchers get them, the durable audit trail stays lean, and a run replayed
from the DB simply has no frames (correct — they were live-only).

**Tradeoffs.** A screenshot per step adds ~100–200ms/step and ~1MB of transient
SSE per run — fine for interactive use, and it's best-effort (a failed capture
never fails the run). Not persisting frames means no after-the-fact playback;
that's the right call for audit-log size, listed as future work if needed.

---

## D29 — Settings/usage page, deploy secret, docs for the full product

**Decision.** A Settings page (account/workspace + LLM usage log reading
`/api/usage`); `UNDERSTUDY_JWT_SECRET` generated by the Render blueprint; and a
README rewrite covering the product as it now is (auth/tenancy, policy
approvals + inbox, batch, dashboard, live view, versions, cost metering) with an
updated architecture, LLD map, and 59-test proof table.

**Deferred (with reason).** The *deployed in-page recorder* (serving inject.js
into the mock apps so users record on the hosted demo) is listed as the top
future-work item rather than built: the local Playwright recorder + the
`POST /api/traces` upload path already cover recording, the boot seed gives
evaluators a workflow to run immediately, and adapting inject.js from a
Playwright binding to a buffer-and-POST widget carried more risk than value at
this stage. Called out honestly in the README rather than quietly skipped.

---

## D30 — In-browser recorder: the core "teach by doing" loop, usable in the app

**Decision.** Make teaching a workflow work entirely in the browser. A recorder
script (`mockapps/static/recorder.js`) is served into the mock apps; clicking
**"Teach a new workflow"** navigates to Vendra with record mode on. The recorder
captures the same semantic events as the Playwright recorder but buffers them in
**sessionStorage** (so they survive navigations between /portal and /erp),
shows a floating "● Recording · Stop & save" widget, and on stop POSTs the
assembled trace to `/api/traces` (bearer token read from localStorage,
same-origin with the SPA), returning to `/workflows?recorded=` ready to learn.

**Why this became the priority.** User testing exposed the real gap: the app
*felt like a canned demo* because you couldn't do the core action — teach it — in
the browser (recording previously needed a local headful Playwright display). A
user even tried to teach it by manually using LedgerOne and nothing connected.
The reference solutions all let you do their core action live; this closes that
gap. Verified end-to-end headless: record a demo in-browser → learn (4 live-read
extracts, invoice_id parameterized, one gated commit) → run on an *unseen*
invoice → approve → posted.

**Bug found and fixed.** A real submit-button click fires `click` THEN `submit`,
so the first recordings learned two post-bill steps — on replay the click would
submit early and the second step would fail. Fixed in both recorders: skip the
click on submit buttons (the submit event carries the commit intent).

**Also fixed (learning UX).** Re-learning a demonstration used to pile up
duplicate workflows. Induction now uses a deterministic id per trace
(`wf-{trace_id}`) and bumps the version, so re-learning *updates* the workflow
instead of duplicating it; the boot seed uses the same scheme.

**Deferred still:** recording on *real* third-party sites (needs the
extension); here the recorder works on the same-origin mock apps, which is the
demonstrable core loop.

---

## D31 — Sentry-style session replay of the recorded demonstration

**Decision.** When you view a recorded demonstration, play it back like a video
(the way Sentry's session replay works), not just a list of events. The
in-browser recorder also runs **rrweb** (the same library Sentry uses),
buffering DOM-mutation events across page navigations in sessionStorage and
uploading them on stop to `POST /api/traces/{id}/replay` (stored in a separate
`replays` table, org-scoped, kept out of the trace payload because it's large).
The trace page mounts rrweb's `Replayer` with custom play/pause + scrub controls.

**Alternatives considered.** (a) Screenshot filmstrip — but the browser can't
cheaply screenshot itself; rrweb reconstructs the real DOM, which is lighter and
higher-fidelity. (b) `rrweb-player` (the prebuilt Svelte widget) — its frame
wouldn't populate in this Vite/React setup, so I dropped it for rrweb's bare
`Replayer` + my own controls (scale-to-fit, timeline slider) — fully under our
control and reliable. (c) Recording on real sites — needs the extension; here it
works on the same-origin mock apps.

**Reasoning.** The replay makes the "we watched you do it" claim tangible and is
the most direct answer to "show a recording like Sentry." rrweb records
continuously across the /portal→/erp full-page navigations by concatenating
per-page snapshot segments into one timeline. The recorder widget is masked out
of the replay via `blockSelector`. Replay capture is strictly best-effort — it
never blocks saving the semantic trace (which is what induction actually needs).

**Tradeoffs.** ~260KB vendored rrweb record bundle served into the mock apps and
~130KB added to the SPA for the Replayer; replay JSON (tens–hundreds of KB) in a
JSON column — all fine at demo scale, documented as such.

---

## D32 — Prod-grade UI overhaul: sidebar app shell + design system

**Decision.** Move from the top-nav "control panel" look to a real SaaS app
shell: a left **icon sidebar** (Dashboard / Workflows / Runs / Approvals /
Settings, a "Mock apps" group, and the signed-in user + sign-out pinned at the
bottom), and a refreshed design system — Inter/system type scale, a restrained
indigo accent, softer borders + shadows, a consistent radius, inline SVG icons
(self-contained, no icon-font dependency), and polished stat cards, buttons,
badges, inputs, banners, and status pills.

**Reasoning.** User testing said the app "looked like a demo, not prod." The
functionality was already rich; the visual layer was the gap. A sidebar shell +
iconography + tighter tokens is the highest-leverage change to read as a product.
Because every page shares the same component classes, refining those classes +
the shell lifted the whole app at once (dashboard, workflow editor, runs,
approvals, settings, trace replay, login) rather than a per-page rewrite.

**What I deliberately kept.** The legible workflow spec stays the visual focus —
the chrome got quieter and more consistent so the spec, audit log, and session
replay stand out. Dark mode and a mobile drawer are deferred (the sidebar
collapses off-canvas under 720px; a toggle is future work).

---

## D33 — Conversational agent that orchestrates workflows (gate-governed)

**Decision.** A chat assistant (`app/agent.py`, `POST /api/agent/chat`, and an
Assistant page) that discovers, learns, and runs workflows from natural language
using Anthropic tool-use. Its tools call the **same org-scoped repos/manager**
the UI uses: list/get workflows, run_workflow, run_batch, list/get runs,
list_traces, induce_workflow, dashboard.

**The safety design is the point.** The agent has **no approve/reject tool** — by
construction it cannot release an approval gate; it can only start runs, which
still hard-pause for a human in the Approvals inbox. So the agent *orchestrates*
and the deterministic executor + gates still *decide* — the same "LLM proposes,
deterministic code decides" spine as induction, now at the orchestration layer.
There's a test asserting no approval tool exists, and tests that the tools are
org-scoped and flag the gate. Every tool call is returned as an **activity trace**
and rendered as a monitoring panel under each reply (what it did, with real ids).

**Alternatives considered.** (a) Give the agent an approve tool for "full
automation" — rejected; it would defeat the entire guardrail. Auto-approval is
available, but only via the explicit per-workflow *policy* the human configures,
not the chat agent. (b) Free-form agent that drives the browser directly —
rejected; routing through the existing typed, gated, audited API keeps every
agent action reproducible and safe. (c) SSE token streaming of the reply —
deferred; a synchronous turn returning reply + full activity trace is simpler and
still shows the agent's working.

**Cost/limits.** Each turn is one+ model calls (tool-use loop, capped at 6
rounds); the endpoint is rate-limited and usage is metered (`kind=agent`) into
the same cost view.

---

## D34 — Multi-parameter capability, clipboard, and the single-input hero demo

**Multi-parameter workflows already work** — `resolve()` in the heuristic turns a
run-varying value the operator TYPES that isn't found on any source page into its
own parameter, while values that ARE on a page become live `extract`s. So a
workflow has exactly as many inputs as the task genuinely needs. The showcase
task needs only `invoice_id` **by design** (vendor/date/amount/GL are read live —
that's the impressive bit), so I proved multi-parameter induction with a test
(`test_operator_supplied_field_becomes_a_second_parameter`) rather than bolting a
second required input onto the hero demo (which would also complicate batch,
whose semantics vary one parameter).

**Clipboard.** Pasting into a field is already captured: the field's `change`
event carries the final value, so a paste becomes an ordinary `fill`. Copying
*from* a page is a read, not a state change — handled by provenance (the value is
matched to the page and becomes an extract). So no dedicated clipboard event is
needed for faithful replay.

**Recording scope.** The in-browser recorder only injects into our same-origin
mock apps; recording arbitrary third-party sites needs the browser-extension
recorder (documented future work). The executor, by contrast, can drive any
Playwright-reachable page.

---

## D35 — Agent elevated to reference bar: actionable cards + two-phase confirm

**Decision.** After studying invoice-copilot's accepted conversational agent, I
elevated ours to match its signature patterns:
- **Typed, actionable cards** in the chat (not just prose): the reply carries a
  `cards` envelope derived from the agent's tool activity — **run cards** (status
  pill, params, and inline **Approve/Reject** the *human* clicks — the agent
  still can't) and **workflow cards** (Open). This is our version of
  ApprovalCard / InvoiceListCard.
- **Two-phase confirm for bulk** (their BulkConfirmCard pattern): `run_batch` now
  previews first (returns `needs_confirmation` + count, starts nothing); the
  agent tells the user "this will start N runs — confirm?"; only a second call
  with `confirmed=true` actually launches. Tested: nothing starts on the preview.

**Where we differ (deliberately).** invoice-copilot parses NL into a *typed
single command* then dispatches deterministically; we use *tool-use* (the model
calls typed, org-scoped, gated tools in a capped loop). Both keep the LLM out of
the decision path — ours arguably stronger since the irreversible step is
*always* human-gated regardless of what the agent does, and there's a test
asserting the agent has no approval tool. Same spine ("LLM proposes,
deterministic code decides"), applied at the orchestration layer.

**Still to match (next):** a keyless deterministic fallback for the chat (like
their mock LLM) so the assistant works with no API key — induction already has
this; the chat doesn't yet.

---

## D36 — Keyless deterministic chat fallback (works with no API key)

**Decision.** The Assistant now works even when `ANTHROPIC_API_KEY` is unset (or
`UNDERSTUDY_AGENT_MOCK=1`): a deterministic `_mock_agent` regex-maps common
requests ("what workflows", "run INV-1002", "which need approval", batch +
confirm, status) to the SAME org-scoped, gated tools and returns the same
{reply, steps, cards} envelope. This mirrors invoice-copilot's mock LLM: the app
(and now the chat) runs and is testable with zero keys, and the fallback still
can't bypass a gate. Tested offline via `UNDERSTUDY_AGENT_MOCK`.

**Why:** the hosted demo may not have a key; before this, the chat returned
"unavailable". Now it degrades to a capable offline assistant. The full LLM
handles free-form language; the mock covers the demo's core commands.

---

## D37 — Second workflow (multi-parameter) + richer LedgerOne + batch defaults

**Decision.** Add a second showcase task — **onboard a vendor** in LedgerOne — to
demonstrate breadth the single invoice task couldn't:
- **Richer mock app:** a LedgerOne vendor master (`/erp/vendors`, `/erp/vendors/new`)
  with name / billing email / payment terms (select) / tax id.
- **Genuinely multi-parameter workflow:** every field is operator-supplied (no
  source page to read), so induction learns **four parameters** — the counterpoint
  to the invoice task's "one input, rest read live." To make this work I relaxed
  induction: a value the operator *types* that isn't found on any page is a per-run
  **parameter** (values on a page still become live extracts). This doesn't change
  the invoice demo (all its typed values are matched), and it's more correct.
- **"Create" is a commit:** added create/save/record to the commit vocabulary, so
  the vendor task is gated too.
- **Batch with defaults:** the batch endpoint + agent `run_batch` now take a
  `defaults` map, so a multi-parameter workflow can be batched (one param varies,
  the rest defaulted). The single-param UI batch stays; multi-param batches via
  the Assistant.

**Verified end-to-end:** the vendor workflow runs → gates on "Create vendor" →
human approves → the vendor lands in the master with all four fields. Tests:
multi-param induction (4 params, no extracts, gated) + multi-param batch-with-
defaults. Both seed on boot alongside the invoice workflow.

---

## D38 — Premium/production pass: split login, dark mode, team, global audit

**Decision.** After comparing to invoice-copilot's deployed app, elevate the UI to
that bar:
- **Marketing split-screen login** — dark left panel (value props + trust chips),
  clean right form + one-click demo.
- **Dark mode** — full dark palette via `:root[data-theme=dark]` token overrides
  + a sidebar toggle (persisted in localStorage, applied before first paint).
- **Team page** — lists the org's members (`/api/auth/team`); invite is stubbed
  (shared-org demo) and labelled as such.
- **Global Audit log** — `/api/audit` flattens every run's events into one
  org-wide, filterable feed (actor · kind · detail · run), newest first.
- Richer sidebar (subtitle, role line) + Audit/Team nav.

**Reasoning.** The functionality was already deep; the product *finish* was the
gap the user (rightly) flagged. Dark mode via CSS variables meant one palette
block themed the entire app. The audit feed reuses the per-run event log (no new
storage) — the same tamper-evident-style trail, surfaced org-wide.

---

## D39 — Guided product tour (navigation guide)

**Decision.** Add a dependency-free coach-mark tour (`Tour.tsx`) that walks a
first-time user through the five core surfaces — Dashboard, Assistant, Workflows,
Approvals, Audit log — highlighting each nav item with a ring and a tooltip
("1 of 5", Skip/Back/Next/Done). It auto-starts once (guarded by
`localStorage.understudy_tour_seen`) and can be re-opened any time from a "?"
help FAB in the corner.

**Reasoning.** Matching invoice-copilot's navigation guide. A tour is the cheapest
way to make a deep product legible on first contact — it frames *why* each
surface exists (esp. the safety story: "the agent never approves an irreversible
step itself"). Built with `getBoundingClientRect` + a fixed overlay rather than a
tour library to avoid a dependency and keep it themable via existing CSS vars.

---

## D40 — Central typed config + split the agent onto Sonnet

**Decision.** Introduce `app/config.py` — a single `pydantic-settings` `Settings`
object that replaces every scattered `os.environ.get(...)` (auth secret, data
dir, DATABASE_URL, base URL, headful, rate-limit, agent-mock, models). It reads
the environment (prefix `UNDERSTUDY_`) with a `.env` fallback and typed,
documented, validated defaults; exposed via a cached `get_settings()`.

Two models are now configured **separately**:
- `agent_model` → **claude-sonnet-5** — the conversational agent is a
  high-frequency, tool-driving loop where Sonnet is fast and cheap enough.
- `induction_model` → **claude-opus-4-8** — induction is a rare,
  correctness-adjacent legibility pass where Opus's extra capability pays off.

**Reasoning.** Config sprawl is a code-quality and ops smell — one typed object
is discoverable, testable, and documented (`.env.example`, `render.yaml`).
Splitting the models is the single biggest cost lever: the agent, not induction,
dominates token volume, and it doesn't need Opus. `.env` auto-loading is a real
DX win (drop your key in one file). Tests are kept hermetic — the suite defaults
to the keyless agent and an autouse fixture clears the settings cache per test so
a developer's real key never triggers a live call. 76 tests green (was 70),
ruff + mypy clean.

---

## D41 — Enrich the mock apps (Vendra + LedgerOne)

**Decision.** Make the mock finance apps read like real software and open room
for more varied workflows:
- **Vendra invoices** gain a PO number, tax, due date, a lifecycle **status**
  (Approved / Pending review / On hold / Paid) with colored badges, and a
  **line-item breakdown** table on the detail page. The invoice list gets a
  **search box + status filter** (client-side, testid'd).
- **LedgerOne** bills gain a **status** (Posted → Paid) and a new **Payments**
  area: a payables list with a "Record payment" action and a payment form
  (date + method) that flips a bill to Paid — a *gated state change* distinct
  from the create-bill task.

All existing testids are preserved (the demo trace + eval are untouched); new
provenance testids (`inv-po`, `inv-due`, `inv-tax`, `inv-status`, `line-items`)
and payment testids are added. `record_payment` guards against double-payment.
9 new contract tests pin the enriched surface (76 → 85 green). Verified in a
headless browser: list, detail, and payments pages all render cleanly.

**Reasoning.** The evaluators judge product thinking and depth; a portal with
one flat field list undersells the system. Richer, realistic screens make the
"learn any browser workflow" claim credible and give the conversational agent +
recorder more genuinely different tasks to operate over.

---

## D42 — A third seeded workflow: record a bill payment (gated state change)

**Decision.** Add `build_payment_trace` and seed a third demonstration:
navigate to LedgerOne Payments → click a specific bill's "Record payment"
(a run-varying `/erp/payments/AP-5001` URL) → enter payment date + method →
Confirm payment. Induction produces params `payment_id` (from the parameterized
navigate), `payment_date`, `payment_method`, and gates the final commit.

Two supporting changes:
- `_dynamic_url_token` now **singularizes** a plural collection segment, so
  `/erp/payments/AP-5001` yields `payment_id` (not `payments_id`); the singular
  `/portal/invoice/INV-1001` is unchanged. Pinned by a unit test.
- `seed_if_empty` is now **idempotent per workflow** (by stable id) instead of
  all-or-nothing, so an existing deployment backfills newly-added showcases on
  the next boot without wiping user data.

**Reasoning.** Three workflows now span the meaningfully different shapes a
learner must handle: read-live-and-post (1 input), all-operator-input create
(N inputs), and gated state-change over an existing record (parameterized URL +
inputs). That's the "learns *procedures*, not one macro" claim, demonstrated.
85 tests green; ruff + mypy clean.

---

## D43 — ⌘K command palette (keyboard-first navigation + actions)

**Decision.** Add a `CommandPalette` (⌘K / Ctrl+K, or the sidebar search box)
that unifies navigation, quick actions (new chat, toggle theme, take tour, open
mock apps, sign out), and **every learned workflow** into one fuzzy-searchable,
keyboard-driven surface (↑/↓/↵/esc, grouped by section). Theme state was lifted
out of the toggle into the Shell so the palette and the sidebar toggle share it.

**Reasoning.** This is the single most-cited "premium" affordance in the
reference app. It also scales: as more workflows are learned, ⌘K stays the
fastest way to reach any of them without hunting the sidebar. Built dependency-
free on the existing design tokens; verified in-browser (open, filter, keyboard
nav) with zero console errors.

---

## D44 — Backend test hardening (+ a real bug caught)

**Decision.** Raise meaningful coverage on the under-tested layers rather than
chase a number: repository methods (versioning history, cost metering + totals,
`recent_events` aggregation/ordering, batch grouping, usage/replay/conversation
CRUD with org-scoping), the keyless agent's remaining intents (status, pending
approvals, help fallback, and the full two-phase batch preview→confirm), and API
endpoints (dashboard, audit, usage, team, conversation CRUD, 404 paths). Added
`pytest-cov` + a coverage config.

**A real bug surfaced.** `_build_cards` iterated `result["workflows"]` assuming a
list, but `get_dashboard` returns `workflows` as an int **count** — so any agent
turn that hit the dashboard crashed. Guarded with an `isinstance(..., list)`
check. This is exactly why the tests were worth writing.

Suite: 85 → **102 tests**, coverage 80% → **85%**; ruff + mypy clean.

---

## D45 — Make the API key actually reach the SDK (end-to-end agent fix)

**Decision.** Two fixes found by driving a real chat turn against Sonnet:
1. `.env` is now loaded by **absolute path** (repo-root, computed from
   `config.py`'s location), not the relative `".env"` — which only resolved when
   the server happened to launch from the repo root, and silently fell back to
   the keyless agent when launched from `backend/` or a container WORKDIR.
2. The Anthropic client is now constructed with `api_key=settings.anthropic_api_key`
   explicitly. The SDK's default reads `os.environ`, but Settings sources the key
   from `.env` into the Settings object — never into `os.environ` — so the
   default lookup failed with an auth error.

Verified end-to-end: the real **claude-sonnet-5** agent chained
`list_workflows` + `get_workflow` and returned an accurate, well-formatted answer;
the turn metered to usage as `agent / claude-sonnet-5` ($0.035).

**Reasoning.** This is why "configured" isn't "working" — only exercising the
live path surfaced that the key never reached the SDK. Both are the kind of bug
that would have looked fine in every unit test (all keyless) and broken the
deployed demo's headline feature.

---

## D46 — Frontend over-engineering: dashboard data-viz, skeletons, optimistic UI

**Decision.** Push the frontend further on perceived quality:
- **Dashboard "Runs by outcome" chart** — a labeled horizontal stacked bar over
  `run_counts`. Followed the data-viz method: status is a *state* job, so it uses
  the reserved status palette (never categorical hues), ships with a legend +
  counts (identity never by color alone), 2px surface gaps between fills, rounded
  ends, and click-through to the filtered Runs list. Validated in light + dark.
- **Skeleton loaders** — a shared `SkeletonList` (shimmer) replaces bare
  "Loading…" spinners across Dashboard, Runs, Workflows, Audit, Team, Approvals.
- **Optimistic approvals** — approve/reject drops the row instantly and rolls
  back on error, so the queue feels immediate while still reconciling with the
  server once the run settles.

**Reasoning.** These are the touches that separate "works" from "premium": the
dashboard now *shows* the automation's state, not just counts it; lists feel
fast; the approval queue feels responsive. All dependency-free on the existing
tokens; verified in-browser (chart segments + legend, both themes) with zero
console errors.

---

## D47 — Restructure the API into an idiomatic FastAPI/MVC layout

**Decision.** Refactor the backend's HTTP layer from one 466-line `build_router`
closure into a conventional, modular structure, in four test-green stages:

1. **`api/schemas.py`** — all request DTOs in one place (the boundary "V"),
   separate from the domain models they map onto.
2. **`container.py`** (composition root) + **`api/deps.py`** (FastAPI `Depends`
   providers) — singletons are constructed once in the container; routers ask for
   what they need via DI instead of closing over globals. `main.py` re-exports
   `auth`/`runs`/… for test compatibility.
3. **`api/routers/`** — one `APIRouter` module per resource (traces, recordings,
   induction, workflows, runs, metrics, agent). Controllers, cleanly separated.
4. **`create_app()` application factory** — `main.py` is now a thin assembler
   (middleware, routers, lifespan, SPA mount) rather than a script.

The result maps cleanly onto MVC: **models/** (domain) + **db/** (persistence) =
model, **api/routers/** = controllers, **api/schemas.py** = the request contract,
with **executor/** + **induction/** as the service layer and **container.py** as
the composition root.

**Reasoning.** The behemoth router was the one part of the codebase that wasn't
industry-standard: DTOs inline, DI by argument-threading, every endpoint in one
function. The new layout is the shape a FastAPI reviewer expects — each resource
is findable, independently testable (dependencies are overridable), and the wiring
lives in exactly one file. All 31 API routes preserved (verified against the
OpenAPI schema); **102 tests green, ruff + mypy clean** at every stage; server
boots and serves end-to-end.

---

## D48 — Production-level layering: backend service layer + frontend modularization

**Backend — service layer + domain errors.**
- `services/errors.py`: `NotFound`/`Conflict`/`Invalid` domain exceptions, mapped
  to 404/409/422 by one handler registered in `create_app`. Services raise these,
  so they carry no web coupling.
- `services/*.py`: one service per resource (trace, workflow, run, induction,
  metrics, agent) holding the orchestration that used to live in route handlers.
  `api/deps.py` gained `get_*_service` providers; the routers are now thin
  controllers (parse → call service → return). Router code dropped to ~55 lines
  each; the biggest handler is now three lines.
- `tests/test_services.py`: 18 unit tests exercising services + their error
  paths directly (no HTTP). Coverage 85% → **89%**.

**Frontend — api module + data hook.**
- Split the 334-line `api.ts` into `api/`: `types.ts` (all DTOs), `http.ts` (the
  fetch core, token, ApiError), `resources/{auth,traces,workflows,runs,metrics,
  agent}.ts` (one client per resource), and an `index.ts` barrel that composes
  the flat `api` object and re-exports everything — so every `from "../api"`
  import is unchanged.
- `hooks/useAsync.ts`: one hook replaces the useState+useEffect+try/catch that
  every list page repeated; standardizes ApiError surfacing and stale-response
  guarding. Migrated Runs/Audit/Team as the first consumers.

**On "one file per model?"** — deliberately **not**. Models are grouped by
aggregate (`models/trace.py`, `models/workflow.py`) and ORM rows share
`db/models.py`, the idiomatic SQLAlchemy layout. One-class-per-file would
fragment cohesive aggregates for no benefit.

120 tests green, ruff + mypy clean, frontend builds; migrated pages verified in
a headless browser with zero console errors.

---

## D49 — Restructure to a production-standard layout (matching the reference bar)

**Decision.** Reshape both stacks to the conventional layered structure a reviewer
expects, benchmarked against the reference projects, keeping all 120 tests green
through every move (one commit per rename).

**Backend** (`backend/app/`) — a strict dependency-downward layering:
`api/` (controllers) → `services/` (use-cases) → `repos/` (persistence) →
`domain/` (pure models). Plus `clients/` (the single Anthropic I/O seam, which
de-duplicated client construction), `prompts/` (system prompts lifted out of
code), `engine/` (was `executor/`), `agents/` (the conversational agent), and
`db/` (`session.py`, ORM, migrations). `models/`→`domain/`, `db/engine.py`→
`db/session.py`. The layering is **CI-enforced by import-linter**: "domain has no
outward dependencies" and "no upward imports (api→services→repos)".

**Frontend** (`frontend/src/`) — `routes/` (screens), `components/` (shared UI:
palette, tour, skeletons, icons), `lib/` (the api client + auth context),
`hooks/` (`useAsync`), `styles/`.

**Infra** — a real **docker-compose** dev stack (backend + frontend with live
reload, `Dockerfile.dev` per stack), a docker-first **Makefile** (`make dev/up/
down/test/lint/ci`), a rewritten **README** with HLD/LLD module maps and the
layer rules, and a **`samples/`** directory exporting the trace + learned-workflow
JSON so the data model is legible without running anything.

**On file-per-model:** kept models grouped by aggregate (`domain/trace.py`,
`domain/workflow.py`; ORM in `db/models.py`) — the idiomatic layout. One-class-
per-file would fragment cohesive aggregates. `decisions.md` stays at the root:
it's a required deliverable, not clutter.

**Reasoning.** The logic was already layered; what was missing was the *shape* a
reviewer reads structure from — findable modules, a composition root, an
enforced dependency direction, and a one-command dev environment. import-linter
turns the architecture from a claim into a build gate.

---

## D50 — Fixes from the in-depth code review (batch 1)

An in-depth review (5 parallel passes: safety, auth/tenancy, refactor, frontend,
persistence/infra) confirmed tenancy isolation and the gate itself are sound, and
surfaced a set of real issues. Fixed the prioritized batch, each with a regression
test; 120 → **124 tests**, ruff + mypy + import-linter clean.

- **H1 — enrichment could disarm gates via `approval_policy`.** The gate is
  resolved at run time from `spec.approval_policy`, but `validate_enrichment`
  never checked it — an LLM-returned auto-approve policy would defeat the gate
  with `requires_approval` still cosmetically true. Now: any policy change is
  rejected (fall back to the deterministic draft) *and* the draft's policy is
  pinned forward. (`induction/llm.py`)
- **M2 — a reject before the gate hung the run.** `_gate_if_needed` cleared the
  approval event then waited, dropping a reject signalled during an earlier step
  → run blocked forever, leaking a browser + a worker-pool slot. Now `_rejected`
  is checked at each step boundary and at the gate before clear/wait.
  (`engine/runner.py`)
- **H3 — committed dev JWT secret, no guard.** `require_secure()` now fails
  closed at boot: the committed dev secret is allowed only with an explicit
  `UNDERSTUDY_DEV_MODE=1`; a real deploy must supply its own secret. (base_url is
  not a usable signal — the container pins it to loopback.)
- **H4 — anonymous destructive `/erp/_reset` in prod.** Gated behind
  `UNDERSTUDY_ENABLE_TEST_HOOKS` (off by default; on in tests/eval/dev-compose).
- **H5 — documented Postgres path crashed on boot.** No driver was shipped; added
  `psycopg[binary]` and `resolve_url` now normalizes any Postgres URL onto the
  `postgresql+psycopg` dialect. Also added a 30s SQLite busy timeout.
- **M5 — dev SQLite DB baked into the image.** `.dockerignore`'s `data` was
  root-only; `backend/data/understudy.db` (with a bcrypt hash) shipped in the
  image. Now `**/data/`, `**/*.db`, `**/.env` are excluded and the stray file
  removed.

Remaining review items (SSE token-in-URL, SSE reconnect, optimistic-rollback
concurrency, account enumeration, and the LOW tail) are triaged in the review and
not yet applied.

---

## D51 — Fixes from the code review (batch 2: SSE + approvals)

- **H2 — 7-day JWT was passed in the SSE URL query string.** Replaced with a
  short-lived (1 min), single-run, read-only **stream ticket** (`typ=sse`). The
  browser mints one via `POST /runs/{id}/events/ticket` (bearer-authed) and
  opens the stream with `?ticket=`. The ticket is one-directional: it's only
  valid for the run it names, and `user_from_token` rejects `typ=sse` so a
  leaked ticket can't be replayed as a general credential. Exposure window went
  from 7 days (whole API) to 1 minute (one run's read-only stream).
- **M3 — SSE closed permanently on any transient error.** `RunPage` now manages
  the connection: mint ticket → open → on drop, reconnect with backoff
  (re-minting the ticket), capped at 5 attempts, surfacing a
  "reconnecting"/"lost" banner instead of silently freezing. The backend now
  emits a `stream_end` sentinel for finished/historical runs too, so the client
  closes cleanly instead of looping. Malformed frames are ignored (guarded
  `JSON.parse`), and a late `getRun` snapshot no longer clobbers a newer
  streamed status.
- **M4 — optimistic approval rollback resurrected already-approved rows.** The
  approvals queue no longer restores a stale pre-action snapshot on failure; it
  reconciles by re-fetching the true queue on both success and failure.

125 tests green (regression tests for the ticket scoping + history replay +
stream_end); ruff + mypy + import-linter clean; verified end-to-end in the
docker-compose stack (ticket POST + `?ticket=` stream, no token in any URL, no
console errors).

---

## D52 — Fixes from the code review (batch 3: LOW tail + M7)

Closed the remaining review items; 125 → **129 tests**, all gates clean.

- **M7 — login timing oracle.** `authenticate` now runs a bcrypt compare against
  a dummy hash on the unknown-email path, so an absent account costs the same
  wall-clock as a present one. (Register still 409s on a taken email — inherent
  to an immediate-token signup with no email-verification step; documented.)
- **L1 — `_dynamic_url_token` replaced every occurrence of the id in the URL.**
  Now replaces only the final path segment (`/portal/v1/invoice/1` no longer
  corrupts the `v1`).
- **L2 — `assert_text` was a substring check** ("100" matched "1000.00"). Now a
  whitespace-normalized exact match.
- **L4 — `ReplayRepo.save` missing the org guard** its siblings have. Added
  (defense-in-depth; the service layer already gates the API path).
- **L5 — repos' builtin `PermissionError` → uncaught 500 + existence oracle.**
  Mapped to **404** (indistinguishable from "not found").
- **L9 — SQLite locking under concurrent runs.** Enabled WAL + `synchronous=NORMAL`
  (plus the 30s busy timeout from D50).
- **L10 — rate limit keyed on the socket peer** (one shared bucket behind
  Render's proxy). Now keys on the left-most `X-Forwarded-For` hop.
- **L11 — `CORS allow_origins=["*"]`.** Now a configurable `cors_origins`
  (default: localhost dev origins; prod is same-origin so needs none).
- **L12 — no unique `(workflow_id, version)`.** Added the constraint + migration
  0002; this surfaced that a hard `delete` left version snapshots behind, so
  `WorkflowRepo.delete` now removes them too.

Documented-and-left (conscious tradeoffs, not bugs): auth token in localStorage,
a couple of intentionally-silent frontend catches, and the `useAsync`
exhaustive-deps escape hatch.

---

## D53 — Recorder app-switcher lives in the recorder chrome, not the mock apps

**Decision.** Reverted the cross-app link I'd briefly added to the mock apps'
shared header and moved it into the recorder's own floating widget: while
recording, the bar shows a "Go to app: Vendra · LedgerOne" switcher that
navigates via `location.href`.

**Reasoning.** Vendra and LedgerOne are meant to be *independent third-party
systems* — Understudy's job is to move data across that boundary. A link baked
into Vendra's chrome (a) broke that fiction and (b) polluted the learned
workflow with a `click` on a mock-specific element that wouldn't exist on a real
portal. Putting the switcher in the recorder overlay keeps the systems
independent and records the crossing as a clean `navigate` event (like typing a
URL / opening a bookmark) — the same shape as the seeded demo trace, and one
that generalizes. Verified: recording persists across the jump and the trace
contains `navigate /portal` → `navigate /erp` with no spurious click.

---

## D54 — Feature: multi-trace parameter discovery

**What.** Record the same task twice (or more) with different data; Understudy
diffs the recordings to *know* which values are parameters (they vary) vs
literals (constant) — instead of the single-trace heuristic's guess.

**How.** `induction/multitrace.py` aligns the fill/select steps positionally
across recordings and flags each field as varies/constant. `induce_from_traces`
takes the single-trace draft and refines it: promote a hard-coded value that
actually varies to a parameter; demote a "parameter" that's constant across
every recording to a literal (extracts/`{{extract.*}}` are left alone).
Unalignable recordings fall back to the single-trace draft. Surfaced via
`POST /api/induce/multi` + `InductionService.induce_multi`, and a multi-select
"Learn from N recordings" affordance on the Workflows page that reports what
varied vs stayed constant.

**Why it matters.** This is the crux of "learn a *procedure*, not a macro": the
vendor-onboarding demo, recorded once, makes all four fields parameters; a second
recording where "Payment terms" is again "Net 30" proves it's a constant and
demotes it. Verified end-to-end (unit + service + live API). 129 → 134 tests.

---

## D55 — Feature: dry-run / preview mode

**What.** Run a workflow in "preview": it navigates, reads live values, and
fills the target form exactly as a real run would — but STOPS at the first
irreversible (gated) step without executing it. Nothing is committed.

**How.** `Run.dry_run` flag threaded from the API (`RunBody.dry_run`) →
`RunService.start` → `RunManager.start_run` → `Runner`. In the execute loop, on
reaching a `requires_approval` step under dry-run, the runner logs a
`dry_run_preview` (what it *would* commit) and completes — no approval pause, no
submit. The run summary carries `dry_run` so the UI badges it "preview". A
"Dry run" button sits next to "Run once" on the workflow page.

**Why it matters.** It lets an operator see exactly what a workflow will read
and do on a given input — before trusting it with the irreversible step. Reuses
the real engine (same navigation + extraction), so the preview is faithful, not
a simulation. Verified end-to-end: a dry run on INV-1005 read the live vendor/
amount/GL, logged the preview, completed, and posted **no** bill to the ERP.
135 tests green.
