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
