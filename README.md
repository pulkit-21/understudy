# Understudy

**An AI teammate that learns a browser workflow by watching you do it once, then runs it for you — under policy, with a human approval gate before anything irreversible, and a full audit trail.**

Built for the *"learn a user's process by watching them, then do it for them"* problem, scoped to the workflow finance-operations teams actually drown in: moving data between systems that don't talk to each other — an invoice portal (**Vendra**) into an ERP (**LedgerOne**).

> **Live demo:** _<paste your deployed URL here after `render.yaml` deploy>_ — click **"Try the live demo"** (no signup).
> **Setup:** `make dev` (Docker) → http://localhost:5173, or `make install && make dev-native` → http://localhost:8000. The app seeds a demo account + three workflows on boot.
> **Decisions log:** [`decisions.md`](decisions.md) — the real calls, alternatives, and trade-offs (start here to see how I think).

---

## Table of contents
- [The demo in one paragraph](#the-demo-in-one-paragraph)
- [What it does](#what-it-does)
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

## What it does

A multi-tenant full-stack product, not a script:

- **Learn by watching** — record a demonstration; induction produces a legible, editable, parameterized workflow spec (deterministic core + optional LLM legibility pass).
- **Run on new data** — give it only an `invoice_id`; every other value is read live off the page. Self-healing locators survive page redesigns.
- **Policy-governed approvals** — per-workflow policy auto-posts small invoices and escalates the rest to a **human approval inbox**; irreversible steps are gated by construction.
- **Conversational agent** — a chat assistant (Claude Sonnet, with a keyless deterministic fallback) that discovers, learns, and runs workflows through the *same org-scoped, gated tools* the UI uses. It can start work but has **no approve tool** — releasing a gate stays human-only, by construction. A ⌘K command palette reaches any workflow, action, or page.
- **Batch & scale** — run a workflow over a list of invoices through a bounded worker pool.
- **Workflow lifecycle** — draft / published / archived, full version history with one-click rollback, duplicate, delete.
- **Dashboard & observability** — KPIs (success rate, pending approvals, time saved, LLM cost), a **live screenshot view** of the agent working, per-run audit trail, run retry, and cost metering.
- **Accounts & tenancy** — bcrypt + JWT auth, org-scoped data isolation, rate limiting. A one-click demo keeps it frictionless to try.

---

## The demo in one paragraph

A user demonstrates once: open the **Vendra** portal, open invoice INV-1001, read its fields, switch to the **LedgerOne** ERP, enter the bill, click *Post bill*. Understudy records **semantic events** (roles, labels, test-ids — never pixel coordinates), induces a **human-readable, parameterized workflow spec**, and can then run that procedure on invoices it has never seen. A run is given **only an invoice id** — vendor, date, amount and GL code are *read live* off each invoice's own page by learned `extract` steps. Because *Post bill* commits state, the induced spec flags it `requires_approval`; every replay **hard-pauses** there until a human approves, and every action lands in an audit log with actor identity (`agent` / `human`) and timestamp.

## Why this scoping

- **Semantic traces, not macros.** RPA-style click recording breaks the moment a page changes. Understudy captures each action as *role + accessible name + data-testid + CSS fallback*, and the executor resolves targets through that chain at replay time (`testid → role+name → css`), reporting when it "healed" via a fallback. There's a test that removes every test-id from the ERP and the workflow still posts the right bill.
- **The learned artifact is legible and editable.** The workflow spec is plain JSON: every step carries a one-sentence `intent`, values reference `{{parameters}}` or `{{extract.*}}` outputs, and risky steps carry `requires_approval`. A finance reviewer can audit the procedure; the UI renders it as an editable list. Trust in the artifact *is* the product.
- **Deterministic first, LLM second.** A heuristic inducer produces a structurally-valid spec offline (testable, reproducible, key-free). An LLM enrichment pass improves naming and — its unique contribution — **provenance**: linking typed values back to the page they were read from, turning them into live `extract` steps. Enrichment is validated against hard invariants (may never remove an approval gate, may never invent selectors) and falls back to the heuristic spec on any violation. The model is called **once per workflow learned (~$0.06)**; every subsequent run is 100% deterministic and costs nothing.
- **Irreversible actions are gated by construction.** `risk: commit` without `requires_approval: true` fails spec validation — at the edit boundary too, so you can't save an ungated commit through the API.

## Quick start

**Docker (recommended)** — full stack with live reload, no local Python/Node needed:

```bash
cp .env.example .env     # optional: add ANTHROPIC_API_KEY to unlock the LLM + agent
make dev                 # build + start backend (:8000) and frontend (:5173)
```

Open **http://localhost:5173** and click **"Try the live demo"** (or register your own workspace).

**Native (no Docker):**

```bash
make install             # venv + backend deps + Chromium + build the React panel
make dev-native          # API + built UI on http://localhost:8000
```

Without an `ANTHROPIC_API_KEY`, induction uses the deterministic heuristic and the agent uses a keyless fallback — identical safety behaviour, plainer wording.

```bash
make test          # 120 tests, incl. the real-Chromium e2e + robustness/policy/tenancy suites
make ci            # ruff + mypy + import-linter + tests (what CI runs)
make eval          # success-rate harness across all invoices + a failure case
make down          # stop the docker stack   (make nuke also drops its volumes)
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
   auth (bcrypt+JWT, org-scoped)  ·  approval policy engine  ·  bounded worker pool
   FastAPI  ──  /api (auth · traces · workflows · runs · batch · dashboard · usage +SSE)
   React panel (dashboard · spec editor · runs · approval inbox · settings)  ·  /portal /erp
   Persistence ──  SQLAlchemy + Alembic  (SQLite default · Postgres via DATABASE_URL)
```

Every data endpoint is behind auth and scoped to the caller's org. **Request flow — learn → run:** record (or seed) a trace → `POST /traces/{id}/induce` produces a `WorkflowSpec` → review/edit it in the panel (`PUT` validates it, `POST /status`, versions/rollback) → `POST /workflows/{id}/runs` (or `/batch`) launches a headless Chromium through the worker pool that walks the spec, streaming its audit log + live screenshots over SSE → at the commit gate the **approval policy** either auto-approves (small amounts, logged as `policy`) or escalates to the human inbox → the bill posts and the run is persisted to history.

## Low-level design (LLD)

**Backend module map** (`backend/app/`) — a layered architecture (dependencies point downward; enforced in CI by `import-linter`):

```
api/          Controllers — thin FastAPI routers (one file per resource), deps.py (DI), schemas.py (request DTOs)
  ↓
services/     Use-cases — orchestration (induction, runs, agent chat, metrics). HTTP-agnostic; raise domain errors.
  ↓
repos/        Repositories — org-scoped persistence, one class per aggregate. The only layer that touches the ORM.
  ↓
domain/       Pure domain models — Trace + WorkflowSpec (steps, params, validate_references). No outward imports.

clients/      I/O seam to the Anthropic API (single place the SDK is built)      prompts/   versioned system prompts
engine/       Runner (policy gates, live frames, audit), self-healing PlaywrightSink, RunManager (bounded worker pool)
agents/       the conversational agent's tool-use loop (tools are the same gated use-cases — no approve tool)
induction/    heuristic.py (deterministic inducer) + llm.py (legibility pass behind hard invariants)
db/           SQLAlchemy models (document-per-row), session, Alembic migrations (run on boot)
core*         config.py (pydantic-settings), container.py (composition root), auth.py (bcrypt+JWT, org=tenant), ratelimit.py
recorder/     inject.js capture (accessible-name, passwords never recorded) + the Playwright demonstration session
mockapps/     Vendra + LedgerOne — deterministic, stable test-ids, ?resilience=drop-testids variant for the self-healing test
```
<sub>*cross-cutting modules live at the package root (`config.py`, `container.py`, `auth.py`, `ratelimit.py`, `main.py`).</sub>

**Layered-architecture rules, CI-enforced.** `import-linter` (see `pyproject.toml`) fails the build if `domain/` ever imports an outer layer, or if a controller/service is imported *upward* (repos importing services, etc.). The dependency direction is a contract, not a convention.

**Frontend module map** (`frontend/src/`)

```
routes/       one file per screen: Dashboard, Workflows, Workflow (spec editor), Run (+ live view),
              Runs, Approvals, Audit, Team, Assistant, Settings, Login
components/    shared UI: CommandPalette (⌘K), Tour (guided onboarding), Skeleton (loaders), Icon
lib/          api/ (typed client — types.ts · http.ts · resources/{auth,traces,workflows,runs,metrics,agent}.ts)
              and auth.tsx (the auth context)
hooks/        useAsync — one hook for fetch/loading/error/reload, replacing per-page boilerplate
styles/       the hand-written CSS design system (light + dark via data-theme tokens)
```

**The workflow IR** — a step's `value` may be a literal, a `{{run_input}}`, or a `{{extract.key}}` (data read live during the run). `validate_references()` catches the three bugs that silently break replays: an undeclared parameter, an `extract` referenced before it's produced, and a `commit` step without a gate.

**Self-healing locator chain** — `PlaywrightSink._locate` tries `data-testid`, then ARIA `role`+accessible-name, then a CSS fallback, and reports which strategy resolved so the audit log can show `healed via role+name`.

**Persistence** — three aggregates (trace, workflow, run) are document-shaped, so each is one row storing the domain model as a JSON payload plus extracted, indexed columns (status, workflow_id, timestamps) for the queries the UI runs. SQLite by default (zero-ops); set `DATABASE_URL` to a `postgres://` URL for Postgres — the repository layer is the only code that touches the ORM.

## Proof it works

**120 tests** (`make test`), 89% line coverage — meaningful, targeting the properties that matter:

| Suite | What it locks down |
|---|---|
| `test_e2e` | Real headless Chromium learns from INV-1001 and posts **INV-1005** (unseen), gate held, ERP row asserted field-for-field. This one test *is* the product. |
| `test_executor` | Gate hard-pauses; rejection stops before commit; `{{extract}}` feeds later fills; an unresolved ref fails the run instead of typing `{{amount}}`. |
| `test_policy` | Auto-approves below threshold (actor=policy); escalates at/above; unparseable amount → human; default always asks; **policy can't remove a commit gate**; awaiting state is persisted (inbox correctness). |
| `test_robustness` | Self-heals when test-ids are removed; unknown invoice fails safely (no post, never gates); mid-run throw settles FAILED without committing; concurrent runs isolated; SSE replays full history to a late subscriber. |
| `test_auth` / `test_batch` | Register/login/me; **HTTP tenant isolation** (org B can't see org A's data); batch fans out one governed run per value; the worker pool bounds concurrency. |
| `test_induction` / `_llm` | Parameterizes to `invoice_id` only; no demo literals leak into steps; enrichment never removes a gate or invents selectors. |
| `test_persistence` | Org-scoped repos round-trip faithfully; version history + rollback; run history survives a server restart; usage/replay/conversation isolation. |
| `test_mockapps` / `test_api` | Auth-gating; PUT refuses an ungated commit (422); lifecycle status/duplicate/delete; versions + rollback; enriched invoice fields + payment lifecycle. |
| `test_services` / `test_config` | Service use-cases + their domain-error paths, tested without the web stack; central Settings resolution (env, model split, derived flags). |

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

**Render (one click):** push to GitHub → New → Blueprint → point at the repo (`render.yaml`). It generates `UNDERSTUDY_JWT_SECRET`; optionally set `ANTHROPIC_API_KEY`. SQLite lives on the container's ephemeral disk (resets on redeploy — fine for a demo); for durability, mount a Render Disk at `/srv/data` or set `DATABASE_URL` to a managed Postgres.

## Scope — what it is and isn't

**Is:** a multi-tenant full-stack product — auth + org isolation, a legible editable IR, deterministic self-healing replay, policy-governed non-bypassable approval gates with a human inbox, batch runs on a bounded pool, a dashboard with live view + cost metering, workflow versioning, an audit trail, real persistence, CI, and a hosted demo.

**Deliberately out of scope** (with reasons in [`decisions.md`](decisions.md)): real third-party sites (SSO, 2FA, CAPTCHA), credential handling, multi-site generalization from a single trace, and a Chrome-extension recorder (the capture script is extension-portable, but store review doesn't fit the timeline; the Playwright demonstration browser is the primary recorder). `contenteditable`, drag-drop, and file uploads in the recorder are known gaps.

## What I'd build next

- **Deployed in-page recorder** — serve `inject.js` into the mock apps (`?record=1`) so a user can record on the hosted demo without a local display.
- **Multi-trace diffing** to infer parameters automatically (record the same task on two invoices → whatever differs is a parameter).
- **Richer approval policy** — per-vendor / per-GL rules and a learning loop (repeated manual approvals become a suggested rule), keeping the tighten-only safety property.
- **LLM locator fallback** as a fourth strategy when all three deterministic locators miss — behind the existing "healed" reporting.
- **Durable, scaled execution** — managed Postgres by default + a persistent run queue (the bounded pool is the current single-node boundary).

## Repository map

```
backend/app/
  api/        controllers — routers/ (per resource), deps.py (DI), schemas.py (request DTOs)
  services/   use-cases (induction, runs, agent, metrics, workflows) + domain errors
  repos/      org-scoped repositories (one class per aggregate)
  domain/     Trace + WorkflowSpec + ApprovalPolicy — the pure IR (start here)
  clients/    Anthropic LLM seam        prompts/   system prompts
  engine/     Runner (policy gates, live frames), self-healing PlaywrightSink, RunManager (worker pool)
  agents/     the conversational agent's tool-use loop
  induction/  heuristic baseline + LLM enrichment (+ cost pricing)
  db/         ORM rows, session, migrations       recorder/  inject.js capture + Playwright session
  mockapps/   Vendra + LedgerOne (deterministic demo stage)
  config.py · container.py · auth.py · ratelimit.py · main.py   (cross-cutting + composition root)
frontend/src/ routes/ · components/ · lib/(api,auth) · hooks/ · styles/
tests/        e2e · executor · policy · robustness · auth · batch · induction · persistence · api · mockapps · services · config
docker-compose.yml · Makefile · Dockerfile(.dev) · render.yaml · scripts/(seed_demo, eval)
samples/      example-trace.json + example-workflow.json — the data model, exported (see samples/README.md)
decisions.md  the running decision log
```

## Tech stack

Python 3.11+ · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 + pydantic-settings · bcrypt + PyJWT + slowapi · Playwright (Chromium) · Anthropic (Claude — Sonnet for the agent, Opus for induction) · React 18 + Vite + TypeScript · ruff + mypy + import-linter + pytest · Docker + docker-compose.
