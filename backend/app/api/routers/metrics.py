"""Metrics — dashboard KPIs, the org-wide audit feed, and the cost meter. Thin
controllers over MetricsService."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services.metrics import MetricsService
from ..deps import User, current_user, get_metrics_service

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user),
              svc: MetricsService = Depends(get_metrics_service)):
    return svc.dashboard(user.org_id)


@router.get("/audit")
def audit_log(user: User = Depends(current_user),
              svc: MetricsService = Depends(get_metrics_service)):
    return svc.audit(user.org_id)


@router.get("/usage")
def usage_log(user: User = Depends(current_user),
              svc: MetricsService = Depends(get_metrics_service)):
    return svc.usage_summary(user.org_id)
