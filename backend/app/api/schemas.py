"""Request DTOs for the HTTP API — the "V" of the boundary: the shapes clients
send in, kept separate from the domain models they eventually touch.

These MUST live at module scope. FastAPI/pydantic v2 cannot build a schema for a
Pydantic model defined inside a function (its qualname carries ``<locals>``) and
silently degrades such a parameter to a query param — which quietly breaks every
body-taking endpoint. Defining them here also keeps that failure mode impossible
by construction.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..domain.workflow import WorkflowStatus


class InduceBody(BaseModel):
    name: str | None = None
    use_llm: bool = True


class InduceMultiBody(BaseModel):
    trace_ids: list[str]             # 2+ recordings of the same task
    name: str | None = None
    use_llm: bool = True


class RunBody(BaseModel):
    params: dict[str, str] = {}


class BatchBody(BaseModel):
    param_values: list[str]          # e.g. a list of invoice ids
    param_key: str | None = None     # which parameter varies; default = sole one
    defaults: dict[str, str] = {}    # values for the workflow's OTHER parameters


class StatusBody(BaseModel):
    status: WorkflowStatus


class StartRecordingBody(BaseModel):
    name: str = "Untitled demonstration"
    start_url: str | None = None


class ReplayBody(BaseModel):
    events: list  # rrweb events


class ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None
