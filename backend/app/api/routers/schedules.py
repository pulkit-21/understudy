"""Schedules — recurring, unattended workflow triggers. Thin controllers over
ScheduleService. A scheduled run still pauses at its approval gate."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services.scheduling import ScheduleService
from ..deps import User, current_user, get_schedule_service
from ..schemas import ScheduleBody, ToggleBody

router = APIRouter(prefix="/api", tags=["schedules"])


@router.get("/schedules")
def list_schedules(user: User = Depends(current_user),
                   svc: ScheduleService = Depends(get_schedule_service)):
    return svc.list(user.org_id)


@router.post("/schedules")
def create_schedule(body: ScheduleBody, user: User = Depends(current_user),
                    svc: ScheduleService = Depends(get_schedule_service)):
    return svc.create(user.org_id, body.workflow_id, body.params,
                      body.interval_minutes)


@router.post("/schedules/{sched_id}/toggle")
def toggle_schedule(sched_id: str, body: ToggleBody,
                    user: User = Depends(current_user),
                    svc: ScheduleService = Depends(get_schedule_service)):
    svc.set_enabled(sched_id, user.org_id, body.enabled)
    return {"ok": True}


@router.delete("/schedules/{sched_id}", status_code=204)
def delete_schedule(sched_id: str, user: User = Depends(current_user),
                    svc: ScheduleService = Depends(get_schedule_service)):
    svc.delete(sched_id, user.org_id)
