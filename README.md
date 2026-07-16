# Understudy

**Watch a person do a browser task once. Learn the procedure — not the clicks. Run it on new data, with a human approval gate before anything irreversible.**

Built for the *"learn a user's process by watching them, then do it for them"* problem, scoped to the workflow finance-operations teams actually drown in: moving data between systems that don't talk to each other — an invoice portal (**Vendra**) into an ERP (**LedgerOne**).

> **Live demo:** _<paste your deployed URL here after `render.yaml` deploy>_
> **Setup:** `make install && make seed && make dev` → http://localhost:8000
> **Decisions log:** [`decisions.md`](decisions.md) — the real calls, alternatives, and trade-offs (start here to see how I think).

---

## Table of contents
- [The demo in one paragraph](#the-demo-in-one-paragraph)
- [Why this scoping](#why-this-scoping)
- [Quick start](#quick-start)
- [Architecture (HLD)](#architecture-hld)
- [Low-level design (LLD)](#low-level-design-lld)
- [Proof it works](#proof-it-works)
- [The hard part I went deep on](#the-hard-part-i-went-deep-on)
- [Deployment](#deployment)
- [Scope — what it is and isn't](#scope--what-it-is-and-isnt)
- [What I'd build next](#what-id-build-next)
- [Repository map](#repository-map)

---

## The demo in one paragraph

A user demonstrates once: open the **Vendra** portal, open invoice INV-1001, read its fields, switch to the **LedgerOne** ERP, enter the bill, click *Post bill*. Understudy records **semantic events** (roles, labels, test-ids — never pixel coordinates), induces a **human-readable, parameterized workflow spec**, and can then run that procedure on invoices it has never seen. A run is given **only an invoice id** — vendor, date, amount and GL code are *read live* off each invoice's own page by learned `extract` steps. Because *Post bill* commits state, the induced spec flags it `requires_approval`; every replay **hard-pauses** there until a human approves, and every action lands in an audit log with actor identity (`agent` / `human`) and timestamp.

## Why this scoping

- **Semantic traces, not macros.** RPA-style click recording breaks the moment a page changes. Understudy captures each action as *role + accessible name + data-testid + CSS fallback*, and the executor resolves targets through that chain at replay time (`testid → role+name → css`), reporting when it "healed" via a fallback. There's a test that removes every test-id from the ERP and the workflow still posts the right bill.
- **The learned artifact is legible and editable.** The workflow spec is plain JSON: every step carries a one-sentence `intent`, values reference `{{parameters}}` or `{{extract.*}}` outputs, and risky steps carry `requires_approval`. A finance reviewer can audit the procedure; the UI renders it as an editable list. Trust in the artifact *is* the product.
- **Deterministic first, LLM second.** A heuristic inducer produces a structurally-valid spec offline (testable, reproducible, key-free). An LLM enrichment pass improves naming and — its unique contribution — **provenance**: linking typed values back to the page they were read from, turning them into live `extract` steps. Enrichment is validated against hard invariants (may never remove an approval gate, may never invent selectors) and falls back to the heuristic spec on any violation. The model is called **once per workflow learned (~$0.06)**; every subsequent run is 100% deterministic and costs nothing.
- **Irreversible actions are gated by construction.** `risk: commit` without `requires_approval: true` fails spec validation — at the edit boundary too, so you can't save an ungated commit through the API.

## Quick start

```bash
make install     # venv + backend deps + Chromium + build the React panel
make seed        # seed the demonstration trace + induced workflow
make dev         # API + UI on http://localhost:8000
```

Optional: `export ANTHROPIC_API_KEY=...` (or a `.env` file) to enable the LLM legibility pass. Without it, induction uses the deterministic heuristic — identical behaviour, plainer step wording.

```bash
make test        # 41 tests, incl. the real-Chromium e2e + robustness suite
make ci          # ruff + mypy + tests (what CI runs)
make eval        # success-rate harness across all invoices + a failure case
docker build -t understudy . && docker run -p 8000:8000 understudy
```

## Architecture (HLD)

One FastAPI service hosts everything — the API, the built React panel (same-origin, no CORS), and two deterministic mock finance apps that stand in for real portals so the demo never depends on a third-party site.

```
                        ┌─────────────────── demonstration ───────────────────┐
   user drives  ──────► │ Playwright browser + inject.js  (semantic capture)   │
   a task once          └──────────────────────────┬───────────────────────────┘
                                                    │  Trace  (semantic events, JSON)
                                                    ▼
                        ┌──────────────── induction ───────────────┐
                        │  heuristic baseline ──► LLM enrichment    │  intents, params,
                        │  (deterministic)        (legibility only) │  provenance/extract
                        └──────────────────────────┬────────────────┘
                                                    │  WorkflowSpec (JSON IR — editable)
                                                    ▼
                        ┌──────────────── execution ────────────────┐
                        │  Runner ──► ActionSink                     │  approval gates,
                        │            ├─ PlaywrightSink (self-healing)│  audit log w/ actor
                        │            └─ FakeSink (tests)             │
                        └──────────────────────────┬────────────────┘
                                                    │  Run + RunEvents (SSE, persisted)
                                                    ▼
   FastAPI  ──  /api (traces · workflows · runs +SSE)  ·  React panel  ·  /portal /erp
   Persistence ──  SQLAlchemy + Alembic  (SQLite default · Postgres via DATABASE_URL)
```

**Request flow — learn → run:** record (or seed) a trace → `POST /traces/{id}/induce` produces a `WorkflowSpec` → review/edit it in the panel (`PUT` validates it) → `POST /workflows/{id}/runs` launches a headless Chromium that walks the spec, streaming its audit log over SSE → it pauses at the commit gate → a human approves → the bill posts and the run is persisted to history.

## Low-level design (LLD)

**Backend module map** (`backend/app/`)
| Module | Responsibility |
|---|---|
| `models/` | The IR: `Trace` (semantic events) + `WorkflowSpec` (steps, params, `validate_references`). Fully typed; start reading here. |
| `recorder/` | `inject.js` capture script (accessible-name computation, input-collapse to FILL, passwords never recorded) + the Playwright demonstration session. |
| `induction/` | `heuristic.py` (deterministic baseline) + `llm.py` (enrichment behind hard safety invariants, falls back on any failure). |
| `executor/` | `Runner` (walks the spec, resolves templates, hard-pauses at gates, emits audit events), `PlaywrightSink` (self-healing locator chain), `RunManager` (one Chromium per run, SSE queues, persistence). |
| `db/` | SQLAlchemy engine, ORM rows (document-per-row: JSON payload + indexed columns), repositories (`save/load/list`), Alembic migrations run on boot. |
| `api/` | REST + SSE. Request bodies are module-scope (a pydantic-v2 gotcha, see D17). |
| `mockapps/` | Vendra + LedgerOne — deterministic, stable test-ids, `?resilience=drop-testids` variant for the self-healing test. |

**The workflow IR** — a step's `value` may be a literal, a `{{run_input}}`, or a `{{extract.key}}` (data read live during the run). `validate_references()` catches the three bugs that silently break replays: an undeclared parameter, an `extract` referenced before it's produced, and a `commit` step without a gate.

**Self-healing locator chain** — `PlaywrightSink._locate` tries `data-testid`, then ARIA `role`+accessible-name, then a CSS fallback, and reports which strategy resolved so the audit log can show `healed via role+name`.

**Persistence** — three aggregates (trace, workflow, run) are document-shaped, so each is one row storing the domain model as a JSON payload plus extracted, indexed columns (status, workflow_id, timestamps) for the queries the UI runs. SQLite by default (zero-ops); set `DATABASE_URL` to a `postgres://` URL for Postgres — the repository layer is the only code that touches the ORM.

## Proof it works

**41 tests** (`make test`) — meaningful, targeting the properties that matter, not coverage:

| Suite | What it locks down |
|---|---|
| `test_e2e` | Real headless Chromium learns from INV-1001 and posts **INV-1005** (unseen), gate held, ERP row asserted field-for-field. This one test *is* the product. |
| `test_executor` | Gate hard-pauses; rejection stops before commit; `{{extract}}` feeds later fills; an unresolved ref fails the run instead of typing `{{amount}}`. |
| `test_robustness` | Self-heals when test-ids are removed; unknown invoice fails safely (no post, never gates); mid-run throw settles FAILED without committing; concurrent runs isolated; SSE replays full history to a late subscriber. |
| `test_induction` / `_llm` | Parameterizes to `invoice_id` only; no demo literals leak into steps; enrichment never removes a gate or invents selectors. |
| `test_persistence` | Repos round-trip faithfully; run history survives a server restart. |
| `test_mockapps` / `test_api` | Contract + error boundaries; PUT refuses an ungated commit (422). |

**Eval harness** (`make eval`) — runs the learned workflow across all seeded invoices, checking each posted bill against the portal's source of truth, plus a failure-mode case:

```
invoice    result detail
INV-1001…INV-1008   PASS   ok        (each: only invoice_id supplied; rest read live)
INV-9999            SAFE   failed safely, nothing posted
------------------------------------------------------------
success rate: 8/8 (100%)  | bad-invoice degrades safely: yes
```

CI (`.github/workflows/ci.yml`) gates every push on ruff + mypy + pytest (with a real Chromium) and a frontend typecheck+build.

## The hard part I went deep on

**Learning the *procedure*, and making a replay that survives the real world.** The easy version records clicks and replays coordinates; it breaks the first time a page shifts. Understudy instead (1) captures semantics, (2) separates *what varies per run* (a single `invoice_id`) from *what's constant*, reading everything else live off the page via provenance-derived `extract` steps, and (3) resolves every target through a self-healing chain. The payoff is tested directly: the ERP form is served **with every `data-testid` stripped** and the learned workflow still posts the correct bill by falling back to accessible role+name — and says so in the audit log. Around that, the safety core is enforced *structurally*: a `commit` step can't be saved without a gate, the gate has no timeout bypass, and unresolved values fail the run rather than typing a template literal into an ERP field.

## Deployment

Single container: a multi-stage `Dockerfile` builds the React panel (node) then serves API + panel + mock apps from the Playwright Python image (Chromium + system deps preinstalled — avoids the usual headless-Chromium failures on PaaS). The app **seeds itself on boot** (offline, no key needed) so a fresh deploy is demoable immediately.

**Render (one click):** push to GitHub → New → Blueprint → point at the repo (`render.yaml`). Optionally set `ANTHROPIC_API_KEY`. SQLite lives on the container's ephemeral disk (resets on redeploy — fine for a demo); for durability, mount a Render Disk at `/srv/data` or set `DATABASE_URL` to a managed Postgres.

## Scope — what it is and isn't

**Is:** a real, tested learn-by-demonstration loop with a legible editable IR, deterministic self-healing replay, non-bypassable approval gates, an audit trail, persistence, and a hosted demo.

**Deliberately out of scope** (with reasons in [`decisions.md`](decisions.md)): real third-party sites (auth, 2FA, CAPTCHA), credential handling, multi-site generalization from a single trace, and a Chrome-extension recorder (the capture script is extension-portable, but store review doesn't fit the timeline; the Playwright demonstration browser is the primary recorder). `contenteditable`, drag-drop, and file uploads in the recorder are known gaps.

## What I'd build next

- **Multi-trace diffing** to infer parameters automatically (record the same task on two invoices → whatever differs is a parameter).
- **LLM locator fallback** as a fourth strategy when all three deterministic locators miss — wired behind the existing "healed" reporting so the happy path stays deterministic and auditable.
- **Chrome-extension recorder** (unpacked) so demonstrations can happen on real internal tools, not just the mock apps.
- **Durable multi-tenant persistence** + a run queue (one Chromium per run is the current single-node boundary).

## Repository map

```
backend/app/models/       Trace + WorkflowSpec (the IR — start here)
backend/app/recorder/     inject.js capture script + Playwright session
backend/app/induction/    heuristic baseline + LLM enrichment
backend/app/executor/     Runner, approval gates, self-healing PlaywrightSink, RunManager
backend/app/db/           engine, ORM rows, repositories, migrations
backend/app/mockapps/     Vendra + LedgerOne (deterministic demo stage)
backend/app/api/          REST + SSE
backend/alembic/          migrations
frontend/src/             React control panel (Vite + TS): workflows, spec editor, run view, runs history, trace view
tests/                    contract · induction · executor · persistence · robustness · e2e
scripts/                  seed_demo.py, eval.py
decisions.md              the running decision log (D1–D25)
```

## Tech stack

Python 3.11+ · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · Playwright (Chromium) · Anthropic (Claude, enrichment only) · React 18 + Vite + TypeScript · ruff + mypy + pytest · Docker.
