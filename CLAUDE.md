# CLAUDE.md — contributor & agent guide

Working context for Claude Code sessions and new contributors. Read `README.md`
first for the product story and architecture; this file is the short operating
manual and the invariants you must not regress.

## What this is

**Understudy** learns a browser workflow by watching a demonstration once, then
runs it on new data — pausing at a human approval gate before anything
irreversible. The showcase domain is finance operations (move a vendor invoice
from a portal into an ERP and post the bill), which is why the demo ships two
deterministic mock apps — **Vendra** (invoice portal) and **LedgerOne** (ERP) —
as a stable, dependency-free stage. The design generalizes beyond that flow;
the mock apps are just a reproducible stand-in for "some website you operate."

## Architecture at a glance

Layered, and enforced (`lint-imports`): `api → services → repos → domain`, with
`clients`/`prompts`/`engine`/`agents` as supporting layers and `container.py` as
the composition root. See the module map in `README.md`. Start reading at
`domain/` (the `Trace` and `WorkflowSpec` IR) — everything else serves that IR.

The pipeline: **record** (`recorder/` + `mockapps/static/recorder.js`) →
**induce** (`induction/`: deterministic heuristic, optional LLM legibility pass,
multi-trace diffing) → **run** (`engine/`: `Runner` walks the spec, gates
irreversible steps, `PlaywrightSink` resolves targets with a self-healing chain)
→ **govern** (approvals, audit, policy, schedules).

## Conventions

- Python 3.11+, Pydantic v2, async throughout the executor/recorder.
- Repositories are the only layer that touches the ORM, and every method is
  org-scoped (multi-tenant isolation is a hard property).
- Services are HTTP-agnostic: they raise the domain errors in
  `services/errors.py`, which a handler maps to status codes. Controllers stay
  thin (parse → call service → return).
- Every risky invariant gets a test. `FakeSink` for executor logic; real
  Chromium only in tests marked `e2e`.
- `make test` / `make lint` before a commit; keep ruff + mypy + import-linter
  green. Config is centralized in `config.py` (`pydantic-settings`); never read
  `os.environ` directly elsewhere.

## Invariants — never weaken these

- **Gates are non-bypassable.** A `requires_approval` step hard-pauses (an
  `asyncio.Event`, no timeout escape) until a human releases it. A form SUBMIT
  is always gated; the LLM enrichment pass may never remove a gate or change the
  approval policy (`validate_enrichment` enforces it; it falls back to the
  deterministic draft on any structural change).
- **The agent cannot approve.** The conversational agent has no approve/reject
  tool — it can start work, only a human releases a gate.
- **Determinism first.** Replays use the spec's literal targets; the LLM locator
  is a last-resort fallback behind the deterministic chain and is reported when
  it fires. An unresolved `{{ref}}` fails the run rather than typing the literal.

## Current status

Feature-complete demo + a production-hardening pass and three feature rounds.
Highlights: multi-tenant auth, persistence (SQLite→Postgres via Alembic), the
in-browser recorder + rrweb replay, conversational agent (Sonnet, keyless
fallback), ⌘K palette, multi-trace induction, dry-run, drift pre-flight + LLM
locator fallback, and scheduling — all gated. **~145 tests; ruff + mypy +
import-linter clean.** The full, dated decision log is in `decisions.md`; the
forward roadmap is the "What I'd build next" section of `README.md`.

## Sharp edges (deliberate boundaries)

- `RunManager` launches one Chromium per run and a gated run holds its slot
  during the human wait — a single-node scaling boundary, documented, not yet
  pooled across nodes.
- The mock ERP state is in-memory and resets on redeploy — intentional for a
  reproducible demo. Destructive/test hooks (e.g. `POST /erp/_reset`) are gated
  behind `UNDERSTUDY_ENABLE_TEST_HOOKS` (off in production).
- The recorder captures clicks/fills/selects/submits and page snapshots; known
  gaps (contenteditable, drag-drop, file uploads) are out of scope and listed.
