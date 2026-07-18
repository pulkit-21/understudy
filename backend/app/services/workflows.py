"""Workflow use-cases: fetch, edit (with validation + version bump), lifecycle
status, duplicate, delete, and version history / rollback."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from ..db.repositories import WorkflowRepo
from ..domain.workflow import WorkflowSpec, WorkflowStatus
from .errors import Invalid, NotFound


class WorkflowService:
    def __init__(self, workflows: WorkflowRepo):
        self.workflows = workflows

    def list(self, org_id: str, include_archived: bool = False) -> list[WorkflowSpec]:
        statuses = None if include_archived else ["draft", "published"]
        return self.workflows.list(org_id, statuses=statuses)

    def get(self, wf_id: str, org_id: str) -> WorkflowSpec:
        spec = self.workflows.load(wf_id, org_id)
        if not spec:
            raise NotFound("workflow not found")
        return spec

    def update(self, wf_id: str, spec: WorkflowSpec, org_id: str) -> WorkflowSpec:
        """Edit surface: version bumps; a spec with reference problems (e.g. a
        commit step that lost its gate) is rejected before it can be saved."""
        existing = self.get(wf_id, org_id)
        problems = spec.validate_references()
        if problems:
            raise Invalid(problems)
        spec.id = wf_id
        spec.version = existing.version + 1
        self.workflows.save(spec, org_id)
        return spec

    def set_status(self, wf_id: str, status: WorkflowStatus,
                   org_id: str) -> WorkflowSpec:
        spec = self.get(wf_id, org_id)
        spec.status = status
        spec.version += 1
        self.workflows.save(spec, org_id)
        return spec

    def duplicate(self, wf_id: str, org_id: str) -> WorkflowSpec:
        spec = self.get(wf_id, org_id)
        spec.id = uuid4().hex[:12]
        spec.name = f"{spec.name} (copy)"
        spec.version = 1
        spec.status = WorkflowStatus.DRAFT
        self.workflows.save(spec, org_id)
        return spec

    def delete(self, wf_id: str, org_id: str) -> None:
        if not self.workflows.delete(wf_id, org_id):
            raise NotFound("workflow not found")

    def versions(self, wf_id: str, org_id: str) -> Sequence[dict]:
        self.get(wf_id, org_id)  # 404 if unknown
        return self.workflows.versions(wf_id, org_id)

    def rollback(self, wf_id: str, version: int, org_id: str) -> WorkflowSpec:
        current = self.get(wf_id, org_id)
        old = self.workflows.version_payload(wf_id, org_id, version)
        if not old:
            raise NotFound("version not found")
        old.id = wf_id
        old.version = current.version + 1  # rollback is a new forward version
        self.workflows.save(old, org_id)
        return old
