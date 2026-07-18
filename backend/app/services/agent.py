"""Conversational-agent use-cases: persisted conversations and the chat turn.

The chat turn is the orchestration that used to sit in the route handler: load
(or open) the conversation, run the tool-use loop, meter cost, and persist both
messages. The agent's tools are org-scoped and cannot approve a gate."""
from __future__ import annotations

from ..config import get_settings
from ..db.repositories import (
    ConversationRepo,
    TraceRepo,
    UsageRepo,
    WorkflowRepo,
)
from ..executor.manager import RunManager
from .errors import NotFound


class AgentService:
    def __init__(self, conversations: ConversationRepo, workflows: WorkflowRepo,
                 runs: RunManager, traces: TraceRepo, usage: UsageRepo):
        self.conversations = conversations
        self.workflows = workflows
        self.runs = runs
        self.traces = traces
        self.usage = usage

    def list_conversations(self, org_id: str) -> list[dict]:
        return self.conversations.list(org_id)

    def get_conversation(self, conv_id: str, org_id: str) -> dict:
        conv = self.conversations.get(conv_id, org_id)
        if conv is None:
            raise NotFound("conversation not found")
        return {"id": conv.id, "title": conv.title, "messages": conv.messages}

    def delete_conversation(self, conv_id: str, org_id: str) -> None:
        if not self.conversations.delete(conv_id, org_id):
            raise NotFound("conversation not found")

    async def chat(self, message: str, conversation_id: str | None,
                   org_id: str) -> dict:
        # imported lazily: the agent module pulls in the Anthropic SDK
        from ..agent import AgentTools, run_agent

        conv = (self.conversations.get(conversation_id, org_id)
                if conversation_id else None)
        if conv is None:
            conv = self.conversations.create(org_id, title=message)
        history = [{"role": m["role"], "content": m["content"]}
                   for m in conv.messages]
        history.append({"role": "user", "content": message})

        tools = AgentTools(self.workflows, self.runs, self.traces,
                           self.usage, org_id)
        result = await run_agent(history, tools)
        if result.get("cost_usd"):
            self.usage.record(org_id, get_settings().agent_model,
                              result.get("input_tokens", 0),
                              result.get("output_tokens", 0),
                              result["cost_usd"], kind="agent")

        conv.messages.append({"role": "user", "content": message})
        conv.messages.append({"role": "assistant", "content": result["reply"],
                              "cards": result.get("cards", []),
                              "steps": result["steps"]})
        self.conversations.save_messages(conv.id, org_id, conv.messages)
        return {"reply": result["reply"], "steps": result["steps"],
                "cards": result.get("cards", []),
                "conversation_id": conv.id, "title": conv.title}
