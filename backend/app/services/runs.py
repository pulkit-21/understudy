"""Run use-cases: launch single/batch runs (with parameter validation), the
approval gate, retry. The SSE stream stays in the router — it is inherently
HTTP (Request lifecycle + StreamingResponse)."""
from __future__ import annotations

from uuid import uuid4

from ..db.repositories import WorkflowRepo
from ..domain.workflow import WorkflowSpec
from ..engine.manager import RunManager
from ..engine.runner import Run
from .errors import Conflict, Invalid, NotFound


class RunService:
    def __init__(self, runs: RunManager, workflows: WorkflowRepo):
        self.runs = runs
        self.workflows = workflows

    def _load_spec(self, wf_id: str, org_id: str) -> WorkflowSpec:
        spec = self.workflows.load(wf_id, org_id)
        if not spec:
            raise NotFound("workflow not found")
        return spec

    def _launch(self, spec: WorkflowSpec, params: dict[str, str], org_id: str,
                batch_id: str | None = None) -> Run:
        missing = [p.key for p in spec.parameters
                   if p.required and p.key not in params]
        if missing:
            raise Invalid(f"missing parameters: {missing}")
        return self.runs.start_run(spec, params, org_id, batch_id=batch_id)

    def start(self, wf_id: str, params: dict[str, str], org_id: str) -> Run:
        return self._launch(self._load_spec(wf_id, org_id), params, org_id)

    def start_batch(self, wf_id: str, param_values: list[str],
                    param_key: str | None, defaults: dict[str, str],
                    org_id: str) -> dict:
        """Fan a workflow out over many inputs; each is its own governed run."""
        spec = self._load_spec(wf_id, org_id)
        key = param_key or (spec.parameters[0].key if spec.parameters else None)
        if key is None:
            raise Invalid("workflow has no parameter to vary")
        batch_id = "batch-" + uuid4().hex[:10]
        run_ids = [self._launch(spec, {**defaults, key: v}, org_id,
                                batch_id=batch_id).id
                   for v in param_values]
        return {"batch_id": batch_id, "run_ids": run_ids, "count": len(run_ids)}

    def list(self, org_id: str, status: str | None = None,
             batch_id: str | None = None) -> list[dict]:
        statuses = [status] if status else None
        return self.runs.list(org_id, statuses=statuses, batch_id=batch_id)

    def get(self, run_id: str, org_id: str) -> Run:
        run = self.runs.get(run_id, org_id)
        if not run:
            raise NotFound("run not found")
        return run

    def approve(self, run_id: str, org_id: str) -> None:
        if not self.runs.approve(run_id, org_id):
            raise Conflict("run is not active")

    def reject(self, run_id: str, org_id: str) -> None:
        if not self.runs.reject(run_id, org_id):
            raise Conflict("run is not active")

    def retry(self, run_id: str, org_id: str) -> Run:
        prev = self.get(run_id, org_id)
        spec = self.workflows.load(prev.workflow_id, org_id)
        if spec is None:
            raise Conflict("the workflow no longer exists")
        return self._launch(spec, prev.params, org_id)
