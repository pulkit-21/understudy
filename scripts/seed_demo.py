"""Seed the data directory with the demonstration trace and its induced
workflow, so a fresh checkout (or the deployed instance) has something to
show before anyone records: the evaluator can immediately run the learned
workflow on an unseen invoice.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import asyncio  # noqa: E402

from app.db import (  # noqa: E402
    SessionLocal, TraceRepo, WorkflowRepo, resolve_url, run_migrations,
)
from app.induction.llm import induce  # noqa: E402
from app.seed import build_demo_trace  # noqa: E402

BASE_URL = os.environ.get("UNDERSTUDY_BASE_URL", "http://localhost:8000")


def main() -> None:
    run_migrations()  # ensure the schema exists before writing

    trace = build_demo_trace(base=BASE_URL)
    trace.id = "demo-seed-001"

    # Full pipeline: deterministic draft, then LLM legibility pass if a key is
    # configured (falls back to the draft otherwise). Either way the structure
    # is identical — the enrichment only improves the human-readable text.
    spec = asyncio.run(induce(trace))
    spec.id = "wf-demo-invoice"

    TraceRepo(SessionLocal).save(trace)
    WorkflowRepo(SessionLocal).save(spec)
    print(f"seeded trace {trace.id} ({len(trace.events)} events) and workflow "
          f"{spec.id} ({len(spec.steps)} steps, params="
          f"{[p.key for p in spec.parameters]}) into {resolve_url()}")


if __name__ == "__main__":
    main()
