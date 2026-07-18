"""Conversational agent — persisted conversations and the chat turn endpoint.
The agent drives the same org-scoped tools the UI uses and can never approve an
irreversible step; only a human releases a gate."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...config import get_settings
from ...db.repositories import (
    ConversationRepo,
    TraceRepo,
    UsageRepo,
    WorkflowRepo,
)
from ...executor.manager import RunManager
from ...ratelimit import limiter
from ..deps import (
    User,
    current_user,
    get_conversations,
    get_runs,
    get_traces,
    get_usage,
    get_workflows,
)
from ..schemas import ChatBody

router = APIRouter(prefix="/api", tags=["agent"])


@router.get("/agent/conversations")
def list_conversations(user: User = Depends(current_user),
                       conversations: ConversationRepo = Depends(get_conversations)):
    return conversations.list(user.org_id)


@router.get("/agent/conversations/{conv_id}")
def get_conversation(conv_id: str, user: User = Depends(current_user),
                     conversations: ConversationRepo = Depends(get_conversations)):
    conv = conversations.get(conv_id, user.org_id)
    if conv is None:
        raise HTTPException(404)
    return {"id": conv.id, "title": conv.title, "messages": conv.messages}


@router.delete("/agent/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, user: User = Depends(current_user),
                        conversations: ConversationRepo = Depends(get_conversations)):
    if not conversations.delete(conv_id, user.org_id):
        raise HTTPException(404)


@router.post("/agent/chat")
@limiter.limit("20/minute")
async def agent_chat(body: ChatBody, request: Request,
                     user: User = Depends(current_user),
                     conversations: ConversationRepo = Depends(get_conversations),
                     workflows: WorkflowRepo = Depends(get_workflows),
                     runs: RunManager = Depends(get_runs),
                     traces: TraceRepo = Depends(get_traces),
                     usage: UsageRepo = Depends(get_usage)):
    from ...agent import AgentTools, run_agent

    # load or start the conversation (persisted history is the source of truth)
    conv = (conversations.get(body.conversation_id, user.org_id)
            if body.conversation_id else None)
    if conv is None:
        conv = conversations.create(user.org_id, title=body.message)
    history = [{"role": m["role"], "content": m["content"]}
               for m in conv.messages]
    history.append({"role": "user", "content": body.message})

    tools = AgentTools(workflows, runs, traces, usage, user.org_id)
    result = await run_agent(history, tools)
    if result.get("cost_usd"):
        usage.record(user.org_id, get_settings().agent_model,
                     result.get("input_tokens", 0),
                     result.get("output_tokens", 0), result["cost_usd"],
                     kind="agent")

    conv.messages.append({"role": "user", "content": body.message})
    conv.messages.append({"role": "assistant", "content": result["reply"],
                          "cards": result.get("cards", []),
                          "steps": result["steps"]})
    conversations.save_messages(conv.id, user.org_id, conv.messages)
    return {"reply": result["reply"], "steps": result["steps"],
            "cards": result.get("cards", []),
            "conversation_id": conv.id, "title": conv.title}
