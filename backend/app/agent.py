"""Conversational agent — an LLM that discovers, learns, and runs workflows on
the user's behalf, using tools that call the SAME org-scoped API the UI uses.

Safety by construction: the agent has NO approve/reject tool. It can start runs,
but an irreversible step still hard-pauses at its approval gate and only a human
can release it in the Approvals inbox. So the agent orchestrates; the
deterministic executor + gates decide. Every tool call is recorded and returned
to the UI as an activity trace (the monitoring panel).
"""
from __future__ import annotations

import contextlib
import json
import re
from typing import Any

from .config import get_settings
from .induction.heuristic import induce_heuristic
from .induction.llm import InductionError, cost_usd, enrich_with_llm

SYSTEM = """\
You are Understudy's assistant. Understudy learns browser workflows from a
recorded demonstration and replays them — the showcase task moves a vendor
invoice from the Vendra portal into the LedgerOne ERP, pausing for human
approval before it posts the bill.

You help the user DISCOVER, LEARN, and RUN these workflows using the provided
tools. Rules you must follow:
- You may START runs (single or batch), but you can NEVER approve or reject an
  irreversible step. Only a human can. When a run pauses for approval, say so
  plainly and tell the user to approve it (on the run card here, or in Approvals).
- For a BATCH, always preview first: call run_batch WITHOUT confirmed, tell the
  user how many runs it will start, and ask them to confirm. Only after they say
  yes, call run_batch again with confirmed=true.
- Prefer acting via tools over guessing. Use real ids returned by tools.
- Be concise and concrete. Report what you did with the ids and statuses.
- If asked to do something you have no tool for, say so."""


def tool_schemas() -> list[dict]:
    return [
        {"name": "list_workflows",
         "description": "List the org's workflows with their parameters and status.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_workflow",
         "description": "Get one workflow's steps, parameters, and approval policy.",
         "input_schema": {"type": "object",
                          "properties": {"workflow_id": {"type": "string"}},
                          "required": ["workflow_id"]}},
        {"name": "run_workflow",
         "description": "Start one run of a workflow. Provide params as a map of "
                        "parameter key -> value. The run may pause at an approval gate.",
         "input_schema": {"type": "object", "properties": {
             "workflow_id": {"type": "string"},
             "params": {"type": "object", "additionalProperties": {"type": "string"}},
         }, "required": ["workflow_id", "params"]}},
        {"name": "run_batch",
         "description": "Run a workflow over many values of one parameter at once. "
                        "Two-phase: call WITHOUT confirmed first to preview the "
                        "count; tell the user and ask them to confirm; then call "
                        "again with confirmed=true to actually start the runs.",
         "input_schema": {"type": "object", "properties": {
             "workflow_id": {"type": "string"},
             "param_key": {"type": "string"},
             "values": {"type": "array", "items": {"type": "string"}},
             "defaults": {"type": "object",
                          "additionalProperties": {"type": "string"},
                          "description": "values for the workflow's OTHER parameters "
                                         "(when it has more than one)"},
             "confirmed": {"type": "boolean",
                           "description": "true only after the user has confirmed"},
         }, "required": ["workflow_id", "values"]}},
        {"name": "list_runs",
         "description": "List recent runs, optionally filtered by status "
                        "(running, awaiting_approval, completed, rejected, failed).",
         "input_schema": {"type": "object",
                          "properties": {"status": {"type": "string"}}}},
        {"name": "get_run",
         "description": "Get a run's status, extracts, and recent audit events.",
         "input_schema": {"type": "object",
                          "properties": {"run_id": {"type": "string"}},
                          "required": ["run_id"]}},
        {"name": "list_traces",
         "description": "List recorded demonstrations that can be turned into workflows.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "induce_workflow",
         "description": "Learn a workflow from a recorded demonstration (trace).",
         "input_schema": {"type": "object",
                          "properties": {"trace_id": {"type": "string"}},
                          "required": ["trace_id"]}},
        {"name": "get_dashboard",
         "description": "Get KPIs: workflow/run counts, pending approvals, cost.",
         "input_schema": {"type": "object", "properties": {}}},
    ]


class AgentTools:
    """Executes tool calls against the org-scoped repos/manager. Returns
    JSON-able results. No approval capability — that's human-only."""

    def __init__(self, workflows, runs, traces, usage, org_id: str):
        self.workflows = workflows
        self.runs = runs
        self.traces = traces
        self.usage = usage
        self.org = org_id

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict:
        fn = getattr(self, f"_{name}", None)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return await fn(args) if _is_async(fn) else fn(args)
        except Exception as e:  # surface tool errors to the model, don't crash
            return {"error": f"{type(e).__name__}: {e}"}

    # ---- read tools ----
    def _list_workflows(self, _):
        return {"workflows": [
            {"id": w.id, "name": w.name, "status": w.status.value,
             "parameters": [{"key": p.key, "description": p.description}
                            for p in w.parameters]}
            for w in self.workflows.list(self.org, statuses=["draft", "published"])]}

    def _get_workflow(self, a):
        w = self.workflows.load(a["workflow_id"], self.org)
        if not w:
            return {"error": "workflow not found"}
        return {"id": w.id, "name": w.name, "description": w.description,
                "parameters": [{"key": p.key, "description": p.description,
                                "example": p.example} for p in w.parameters],
                "approval_policy": w.approval_policy.model_dump(mode="json"),
                "steps": [{"intent": s.intent, "action": s.action.value,
                           "risk": s.risk.value,
                           "requires_approval": s.requires_approval}
                          for s in w.steps]}

    def _list_runs(self, a):
        return {"runs": self.runs.list(self.org,
                                       statuses=[a["status"]] if a.get("status") else None,
                                       limit=20)}

    def _get_run(self, a):
        run = self.runs.get(a["run_id"], self.org)
        if not run:
            return {"error": "run not found"}
        return {"id": run.id, "status": run.status.value,
                "params": run.params, "extracts": run.extracts,
                "recent_events": [{"kind": e.kind, "actor": e.actor, "detail": e.detail}
                                  for e in run.events[-8:]]}

    def _list_traces(self, _):
        return {"traces": [{"id": t.id, "name": t.name, "events": len(t.events)}
                           for t in self.traces.list(self.org)]}

    def _get_dashboard(self, _):
        counts = self.runs.repo.counts_by_status(self.org)
        return {"workflows": len(self.workflows.list(self.org, statuses=["draft", "published"])),
                "run_counts": counts,
                "pending_approvals": counts.get("awaiting_approval", 0),
                "cost_usd": round(self.usage.total(self.org), 4)}

    # ---- action tools (start work; never approve) ----
    def _run_workflow(self, a):
        spec = self.workflows.load(a["workflow_id"], self.org)
        if not spec:
            return {"error": "workflow not found"}
        params = a.get("params", {})
        missing = [p.key for p in spec.parameters if p.required and p.key not in params]
        if missing:
            return {"error": f"missing required parameters: {missing}"}
        run = self.runs.start_run(spec, params, self.org)
        gated = any(s.requires_approval for s in spec.steps)
        return {"run_id": run.id, "status": run.status.value,
                "note": ("This run will pause at an approval gate; a human must "
                         "approve it in the Approvals inbox before it commits."
                         if gated else "This run has no approval gate.")}

    def _run_batch(self, a):
        spec = self.workflows.load(a["workflow_id"], self.org)
        if not spec:
            return {"error": "workflow not found"}
        key = a.get("param_key") or (spec.parameters[0].key if spec.parameters else None)
        if not key:
            return {"error": "workflow has no parameter to vary"}
        values = a["values"]
        # two-phase: preview first, execute only after the user confirms
        if not a.get("confirmed"):
            return {"needs_confirmation": True, "count": len(values),
                    "values": values, "workflow": spec.name,
                    "note": f"This will start {len(values)} runs of '{spec.name}'. "
                            "Ask the user to confirm, then call run_batch again "
                            "with confirmed=true."}
        from uuid import uuid4
        batch = "batch-" + uuid4().hex[:10]
        defaults = a.get("defaults") or {}
        ids = [self.runs.start_run(spec, {**defaults, key: v}, self.org, batch_id=batch).id
               for v in a["values"]]
        return {"batch_id": batch, "run_ids": ids, "count": len(ids),
                "note": "Runs execute under the workflow's approval policy; any "
                        "that aren't auto-approved wait in the Approvals inbox."}

    async def _induce_workflow(self, a):
        t = self.traces.load(a["trace_id"], self.org)
        if not t:
            return {"error": "trace not found"}
        spec = induce_heuristic(t)
        with contextlib.suppress(InductionError):
            spec = await enrich_with_llm(
                t, spec,
                on_usage=lambda u: self.usage.record(
                    self.org, u["model"], u["input_tokens"],
                    u["output_tokens"], u["cost_usd"]))
        spec.id = f"wf-{a['trace_id']}"
        existing = self.workflows.load(spec.id, self.org)
        if existing:
            spec.version = existing.version + 1
        self.workflows.save(spec, self.org)
        return {"workflow_id": spec.id, "name": spec.name,
                "steps": len(spec.steps),
                "parameters": [p.key for p in spec.parameters]}


def _is_async(fn) -> bool:
    import inspect
    return inspect.iscoroutinefunction(fn)


def _dedup(xs: list[str]) -> list[str]:
    seen, out = set(), []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _build_cards(tools: AgentTools, steps: list[dict]) -> list[dict]:
    """Turn the agent's tool activity into actionable cards the chat can render
    (run cards with inline approve/reject for the human; workflow cards). Fetched
    fresh so statuses are current."""
    run_ids: list[str] = []
    wf_ids: list[str] = []
    for s in steps:
        r = s.get("result") or {}
        inp = s.get("input") or {}
        if isinstance(r, dict):
            if r.get("run_id"):
                run_ids.append(r["run_id"])
            run_ids += [x for x in r.get("run_ids", []) if isinstance(x, str)]
            for run in r.get("runs", []):
                if isinstance(run, dict) and run.get("id"):
                    run_ids.append(run["id"])
            if s["tool"] == "get_run" and r.get("id"):
                run_ids.append(r["id"])
            for w in r.get("workflows", []):
                if isinstance(w, dict) and w.get("id"):
                    wf_ids.append(w["id"])
            if r.get("workflow_id") and s["tool"] == "induce_workflow":
                wf_ids.append(r["workflow_id"])
            if s["tool"] == "get_workflow" and r.get("id"):
                wf_ids.append(r["id"])
        if isinstance(inp, dict) and inp.get("workflow_id"):
            wf_ids.append(inp["workflow_id"])

    cards: list[dict] = []
    for rid in _dedup(run_ids)[:8]:
        run = tools.runs.get(rid, tools.org)
        if run:
            cards.append({"type": "run", "id": run.id,
                          "status": run.status.value, "params": run.params,
                          "workflow_id": run.workflow_id})
    for wid in _dedup(wf_ids)[:6]:
        w = tools.workflows.load(wid, tools.org)
        if w:
            cards.append({"type": "workflow", "id": w.id, "name": w.name,
                          "param_keys": [p.key for p in w.parameters]})
    return cards


_AFFIRM = re.compile(r"\b(yes|confirm|proceed|go ahead|do it|sure|ok|okay)\b", re.I)
_INV = re.compile(r"\bINV-?\d+\b", re.I)


def _invoice_ids(text: str) -> list[str]:
    out = []
    for m in _INV.findall(text or ""):
        m = m.upper()
        out.append(m if m.startswith("INV-") else "INV-" + m[3:])
    return _dedup(out)


async def _mock_agent(history: list[dict], tools: AgentTools) -> dict:
    """Deterministic, keyless fallback (no API key needed) — mirrors the
    reference's mock LLM. Regex-maps common requests to the SAME gated tools, so
    the assistant still works (and is testable) offline. Not as flexible as the
    LLM, but never bypasses a gate."""
    steps: list[dict] = []

    async def call(name, args):
        r = await tools.dispatch(name, args)
        steps.append({"tool": name, "input": args, "result": r})
        return r

    def done(reply):
        return {"reply": reply, "steps": steps, "cards": _build_cards(tools, steps),
                "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}

    last = (history[-1]["content"] if history else "")
    low = last.lower()
    ids = _invoice_ids(last)

    async def _first_wf():
        wf = await call("list_workflows", {})
        return (wf.get("workflows") or [None])[0]

    # confirm a previously-previewed batch (scan history for the invoice ids)
    if _AFFIRM.search(low) and not ids:
        prior: list[str] = []
        for m in reversed(history[:-1]):
            prior = _invoice_ids(m.get("content", ""))
            if prior:
                break
        if not prior:
            return done("There's nothing pending to confirm. Try “run the invoice "
                        "workflow on INV-1002”.")
        wf = await _first_wf()
        if not wf:
            return done("There are no workflows yet — learn one first.")
        key = (wf["parameters"] or [{"key": "invoice_id"}])[0]["key"]
        res = await call("run_batch", {"workflow_id": wf["id"], "param_key": key,
                                       "values": prior, "confirmed": True})
        return done(f"Started {res.get('count', 0)} runs. Each pauses for your "
                    "approval — release them on the run cards or in Approvals.")

    # list workflows
    if "workflow" in low and any(w in low for w in
                                 ["what", "which", "list", "show", "have", "any"]):
        wf = await call("list_workflows", {})
        names = ", ".join(w["name"] for w in wf["workflows"]) or "none yet"
        return done(f"You have {len(wf['workflows'])} workflow(s): {names}.")

    # what's awaiting approval
    if any(w in low for w in ["approv", "waiting", "pending"]):
        r = await call("list_runs", {"status": "awaiting_approval"})
        n = len(r["runs"])
        return done(f"{n} run(s) are waiting for your approval — review them below."
                    if n else "Nothing is waiting for approval right now. 🎉")

    # run on invoice(s)
    if ids:
        wf = await _first_wf()
        if not wf:
            return done("There are no workflows yet — learn one from a demonstration first.")
        key = (wf["parameters"] or [{"key": "invoice_id"}])[0]["key"]
        if len(ids) == 1:
            await call("run_workflow", {"workflow_id": wf["id"], "params": {key: ids[0]}})
            return done(f"Started a run for {ids[0]} — it will pause for your "
                        "approval before posting. You can approve it below.")
        await call("run_batch", {"workflow_id": wf["id"], "param_key": key, "values": ids})
        return done(f"This will start {len(ids)} runs for {', '.join(ids)}. "
                    "Reply “yes” to proceed.")

    # status / dashboard
    if any(w in low for w in ["status", "dashboard", "summary", "how many", "how are"]):
        d = await call("get_dashboard", {})
        return done(f"{d['workflows']} workflow(s), {sum(d['run_counts'].values())} "
                    f"run(s), {d['pending_approvals']} awaiting approval.")

    return done("I can list your workflows, run one on an invoice (e.g. “run "
                "INV-1002”), run a batch, and show what's awaiting approval. "
                "(This is the offline fallback; set ANTHROPIC_API_KEY for the full "
                "LLM assistant.)")


async def run_agent(history: list[dict], tools: AgentTools) -> dict:
    """Run the tool-use loop for one user turn. Returns the assistant reply plus
    an activity trace of every tool call (name, input, result) for the monitor.
    Falls back to a deterministic keyless agent when no API key is configured."""
    settings = get_settings()
    if settings.use_mock_agent:
        return await _mock_agent(history, tools)
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return await _mock_agent(history, tools)

    model = settings.agent_model
    client = AsyncAnthropic()
    convo: list[dict] = [{"role": m["role"], "content": m["content"]}
                         for m in history]
    schemas = tool_schemas()
    steps: list[dict] = []
    in_tok = out_tok = 0

    for _ in range(6):  # cap tool-use rounds
        msg = await client.messages.create(
            model=model, max_tokens=1500, system=SYSTEM,
            tools=schemas,  # type: ignore[arg-type]
            messages=convo,  # type: ignore[arg-type]
        )
        in_tok += msg.usage.input_tokens
        out_tok += msg.usage.output_tokens

        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        tool_uses = [b for b in msg.content if b.type == "tool_use"]

        if not tool_uses:
            return {"reply": text or "(no response)", "steps": steps,
                    "cards": _build_cards(tools, steps),
                    "cost_usd": cost_usd(model, in_tok, out_tok),
                    "input_tokens": in_tok, "output_tokens": out_tok}

        # record the assistant turn (text + tool_use blocks) verbatim
        convo.append({"role": "assistant", "content": [b.model_dump() for b in msg.content]})
        results = []
        for tu in tool_uses:
            result = await tools.dispatch(tu.name, tu.input or {})
            steps.append({"tool": tu.name, "input": tu.input, "result": result})
            results.append({"type": "tool_result", "tool_use_id": tu.id,
                            "content": json.dumps(result)[:4000]})
        convo.append({"role": "user", "content": results})

    return {"reply": "I did several steps but stopped to avoid looping — check "
                     "the activity trace and Runs.", "steps": steps,
            "cards": _build_cards(tools, steps),
            "cost_usd": cost_usd(model, in_tok, out_tok),
            "input_tokens": in_tok, "output_tokens": out_tok}
