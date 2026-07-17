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
