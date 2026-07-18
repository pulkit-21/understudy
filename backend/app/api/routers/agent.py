"""Conversational agent — persisted conversations and the chat turn. Thin
controllers over AgentService."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...ratelimit import limiter
from ...services.agent import AgentService
from ..deps import User, current_user, get_agent_service
from ..schemas import ChatBody

router = APIRouter(prefix="/api", tags=["agent"])


@router.get("/agent/conversations")
def list_conversations(user: User = Depends(current_user),
                       svc: AgentService = Depends(get_agent_service)):
    return svc.list_conversations(user.org_id)


@router.get("/agent/conversations/{conv_id}")
def get_conversation(conv_id: str, user: User = Depends(current_user),
                     svc: AgentService = Depends(get_agent_service)):
    return svc.get_conversation(conv_id, user.org_id)


@router.delete("/agent/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, user: User = Depends(current_user),
                        svc: AgentService = Depends(get_agent_service)):
    svc.delete_conversation(conv_id, user.org_id)


@router.post("/agent/chat")
@limiter.limit("20/minute")
async def agent_chat(body: ChatBody, request: Request,
                     user: User = Depends(current_user),
                     svc: AgentService = Depends(get_agent_service)):
    return await svc.chat(body.message, body.conversation_id, user.org_id)
