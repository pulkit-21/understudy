"""Recording — spawns a headful demonstration browser on the *local* host. On a
headless server the in-page recorder (served into the mock apps) is used instead
and POSTs its trace to /api/traces.

This is infrastructure, not a domain use-case (it owns a live browser process),
so it stays a router over process-local state rather than a service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...config import get_settings
from ...ratelimit import limiter
from ...recorder.session import RecordingSession
from ...services.errors import NotFound
from ...services.traces import TraceService
from ..deps import User, current_user, get_trace_service
from ..schemas import StartRecordingBody

router = APIRouter(prefix="/api", tags=["recordings"])

# In-flight local recording sessions, keyed by trace id. Process-local by design:
# a headful browser only exists on the host that launched it.
_active: dict[str, RecordingSession] = {}


@router.post("/recordings/start")
@limiter.limit("10/minute")
async def start_recording(request: Request, body: StartRecordingBody,
                          user: User = Depends(current_user)):
    base = get_settings().base_url
    start_url = body.start_url or f"{base}/portal"
    session = RecordingSession(name=body.name, start_url=start_url)
    try:
        await session.start()          # opens the headful window
    except Exception as e:
        raise HTTPException(
            503,
            "could not launch the demonstration browser "
            f"({type(e).__name__}: {e}). Local recording needs a display; "
            "on a headless host, record via the in-page recorder and POST "
            "the trace to /api/traces.",
        ) from e
    _active[session.trace.id] = session
    return {"recording_id": session.trace.id,
            "name": session.trace.name, "start_url": start_url}


@router.get("/recordings")
def list_recordings(user: User = Depends(current_user)):
    return [{"recording_id": rid, "name": s.trace.name,
             "events": len(s.trace.events)}
            for rid, s in _active.items()]


@router.post("/recordings/{recording_id}/stop")
async def stop_recording(recording_id: str,
                         user: User = Depends(current_user),
                         traces: TraceService = Depends(get_trace_service)):
    session = _active.pop(recording_id, None)
    if session is None:
        raise NotFound("no active recording with that id")
    trace = await session.stop()
    return traces.save(trace, user.org_id)
