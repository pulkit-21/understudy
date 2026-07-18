import { req } from "../http";
import { AgentCard, AgentStep, ChatMsg } from "../types";

export const agentApi = {
  chat: (message: string, conversation_id?: string) =>
    req<{ reply: string; steps: AgentStep[]; cards: AgentCard[];
          conversation_id: string; title: string }>("/api/agent/chat", {
      method: "POST", body: JSON.stringify({ message, conversation_id }),
    }),
  listConversations: () =>
    req<{ id: string; title: string; updated_at: string; messages: number }[]>(
      "/api/agent/conversations"),
  getConversation: (id: string) =>
    req<{ id: string; title: string; messages: ChatMsg[] }>(
      `/api/agent/conversations/${id}`),
  deleteConversation: (id: string) =>
    req<void>(`/api/agent/conversations/${id}`, { method: "DELETE" }),
};
