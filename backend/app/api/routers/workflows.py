"""Workflows — the learned procedures. Thin controllers over WorkflowService."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...domain.workflow import WorkflowSpec
from ...services.workflows import WorkflowService
from ..deps import User, current_user, get_workflow_service
from ..schemas import StatusBody

router = APIRouter(prefix="/api", tags=["workflows"])


@router.get("/workflows")
def list_workflows(user: User = Depends(current_user),
                   include_archived: bool = False,
                   svc: WorkflowService = Depends(get_workflow_service)):
    return svc.list(user.org_id, include_archived)


@router.get("/workflows/{wf_id}")
def get_workflow(wf_id: str, user: User = Depends(current_user),
                 svc: WorkflowService = Depends(get_workflow_service)):
    return svc.get(wf_id, user.org_id)


@router.put("/workflows/{wf_id}")
def update_workflow(wf_id: str, spec: WorkflowSpec,
                    user: User = Depends(current_user),
                    svc: WorkflowService = Depends(get_workflow_service)):
    return svc.update(wf_id, spec, user.org_id)


@router.post("/workflows/{wf_id}/status")
def set_status(wf_id: str, body: StatusBody,
               user: User = Depends(current_user),
               svc: WorkflowService = Depends(get_workflow_service)):
    return svc.set_status(wf_id, body.status, user.org_id)


@router.post("/workflows/{wf_id}/duplicate")
def duplicate_workflow(wf_id: str, user: User = Depends(current_user),
                       svc: WorkflowService = Depends(get_workflow_service)):
    return svc.duplicate(wf_id, user.org_id)


@router.delete("/workflows/{wf_id}", status_code=204)
def delete_workflow(wf_id: str, user: User = Depends(current_user),
                    svc: WorkflowService = Depends(get_workflow_service)):
    svc.delete(wf_id, user.org_id)


@router.get("/workflows/{wf_id}/versions")
def list_versions(wf_id: str, user: User = Depends(current_user),
                  svc: WorkflowService = Depends(get_workflow_service)):
    return svc.versions(wf_id, user.org_id)


@router.post("/workflows/{wf_id}/rollback/{version}")
def rollback(wf_id: str, version: int, user: User = Depends(current_user),
             svc: WorkflowService = Depends(get_workflow_service)):
    return svc.rollback(wf_id, version, user.org_id)
