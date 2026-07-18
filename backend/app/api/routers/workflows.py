"""Workflows — the learned procedures. CRUD plus the edit surface (PUT with
reference validation), lifecycle status, duplicate, and immutable version
history with rollback."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from ...db.repositories import WorkflowRepo
from ...models.workflow import WorkflowSpec, WorkflowStatus
from ..deps import User, current_user, get_workflows
from ..schemas import StatusBody

router = APIRouter(prefix="/api", tags=["workflows"])


@router.get("/workflows")
def list_workflows(user: User = Depends(current_user),
                   include_archived: bool = False,
                   workflows: WorkflowRepo = Depends(get_workflows)):
    statuses = None if include_archived else ["draft", "published"]
    return workflows.list(user.org_id, statuses=statuses)


@router.get("/workflows/{wf_id}")
def get_workflow(wf_id: str, user: User = Depends(current_user),
                 workflows: WorkflowRepo = Depends(get_workflows)):
    spec = workflows.load(wf_id, user.org_id)
    if not spec:
        raise HTTPException(404)
    return spec


@router.put("/workflows/{wf_id}")
def update_workflow(wf_id: str, spec: WorkflowSpec,
                    user: User = Depends(current_user),
                    workflows: WorkflowRepo = Depends(get_workflows)):
    """The edit surface: the UI PUTs the modified spec back. Version bumps;
    reference problems are returned so the UI can block a broken save."""
    existing = workflows.load(wf_id, user.org_id)
    if not existing:
        raise HTTPException(404)
    problems = spec.validate_references()
    if problems:
        raise HTTPException(422, detail=problems)
    spec.id = wf_id
    spec.version = existing.version + 1
    workflows.save(spec, user.org_id)
    return spec


@router.post("/workflows/{wf_id}/status")
def set_status(wf_id: str, body: StatusBody,
               user: User = Depends(current_user),
               workflows: WorkflowRepo = Depends(get_workflows)):
    spec = workflows.load(wf_id, user.org_id)
    if not spec:
        raise HTTPException(404)
    spec.status = body.status
    spec.version += 1
    workflows.save(spec, user.org_id)
    return spec


@router.post("/workflows/{wf_id}/duplicate")
def duplicate_workflow(wf_id: str, user: User = Depends(current_user),
                       workflows: WorkflowRepo = Depends(get_workflows)):
    spec = workflows.load(wf_id, user.org_id)
    if not spec:
        raise HTTPException(404)
    spec.id = uuid4().hex[:12]
    spec.name = f"{spec.name} (copy)"
    spec.version = 1
    spec.status = WorkflowStatus.DRAFT
    workflows.save(spec, user.org_id)
    return spec


@router.delete("/workflows/{wf_id}", status_code=204)
def delete_workflow(wf_id: str, user: User = Depends(current_user),
                    workflows: WorkflowRepo = Depends(get_workflows)):
    if not workflows.delete(wf_id, user.org_id):
        raise HTTPException(404)


@router.get("/workflows/{wf_id}/versions")
def list_versions(wf_id: str, user: User = Depends(current_user),
                  workflows: WorkflowRepo = Depends(get_workflows)):
    if not workflows.load(wf_id, user.org_id):
        raise HTTPException(404)
    return workflows.versions(wf_id, user.org_id)


@router.post("/workflows/{wf_id}/rollback/{version}")
def rollback(wf_id: str, version: int, user: User = Depends(current_user),
             workflows: WorkflowRepo = Depends(get_workflows)):
    current = workflows.load(wf_id, user.org_id)
    old = workflows.version_payload(wf_id, user.org_id, version)
    if not current or not old:
        raise HTTPException(404)
    old.id = wf_id
    old.version = current.version + 1  # rollback is a new forward version
    workflows.save(old, user.org_id)
    return old
