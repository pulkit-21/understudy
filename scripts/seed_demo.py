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

from app.induction.llm import induce  # noqa: E402
from app.recorder.session import TraceStore  # noqa: E402
from app.api.routes import WorkflowStore  # noqa: E402
from tests.conftest import demo_trace  # noqa: E402

BASE_URL = os.environ.get("UNDERSTUDY_BASE_URL", "http://localhost:8000")
DATA = Path(os.environ.get("UNDERSTUDY_DATA", ROOT / "data"))


def main() -> None:
    trace = demo_trace.__wrapped__()
    for e in trace.events:
        e.url = e.url.replace("http://localhost:8000", BASE_URL)
    trace.id = "demo-seed-001"

    # Full pipeline: deterministic draft, then LLM legibility pass if a key is
    # configured (falls back to the draft otherwise). Either way the structure
    # is identical — the enrichment only improves the human-readable text.
    spec = asyncio.run(induce(trace))
    spec.id = "wf-demo-invoice"

    TraceStore(DATA / "traces").save(trace)
    WorkflowStore(DATA / "workflows").save(spec)
    print(f"seeded trace {trace.id} ({len(trace.events)} events) and workflow "
          f"{spec.id} ({len(spec.steps)} steps, params="
          f"{[p.key for p in spec.parameters]}) into {DATA}")


if __name__ == "__main__":
    main()
