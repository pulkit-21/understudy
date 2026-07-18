"""Domain errors + their HTTP mapping.

Services raise these instead of `HTTPException`, so they carry no web-framework
coupling and can be unit-tested directly. `register_error_handlers(app)` wires a
handler per type onto the FastAPI app, translating each to the right status code.
The status mapping lives here, in one place, rather than scattered across routes.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ServiceError(Exception):
    """Base for all domain errors. `status` is the HTTP code it maps to;
    `detail` is the response body's `detail` field."""

    status: int = 400

    def __init__(self, detail: Any = None):
        self.detail = detail if detail is not None else self.__class__.__name__
        super().__init__(str(self.detail))


class NotFound(ServiceError):
    """A referenced resource does not exist (in this org)."""

    status = 404


class Conflict(ServiceError):
    """The request is valid but conflicts with current state (e.g. approving a
    run that is no longer active)."""

    status = 409


class Invalid(ServiceError):
    """The request is well-formed but semantically invalid (e.g. missing
    required parameters, a spec whose commit step lost its gate)."""

    status = 422


def register_error_handlers(app: FastAPI) -> None:
    async def _handle(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    # One registration per concrete type keeps Starlette's handler lookup exact.
    for exc_type in (NotFound, Conflict, Invalid, ServiceError):
        app.add_exception_handler(exc_type, _handle)  # type: ignore[arg-type]
