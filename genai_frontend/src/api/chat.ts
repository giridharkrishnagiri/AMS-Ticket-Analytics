import { requestJson } from "./client";
import type {
  ChatSession,
  ChatSessionDetail,
  ChatSessionList,
  ContextOption,
  CreateChatSessionPayload,
  SendChatMessagePayload,
  SendChatMessageResponse,
  UpdateChatSessionPayload
} from "../types/chat";

export type ChatSessionFilters = {
  customerId?: string | null;
  projectId?: string | null;
  includeArchived?: boolean;
  limit?: number;
  offset?: number;
};

function chatSessionQuery(filters: ChatSessionFilters): string {
  const params = new URLSearchParams();
  if (filters.customerId) {
    params.set("customer_id", filters.customerId);
  }
  if (filters.projectId) {
    params.set("project_id", filters.projectId);
  }
  if (filters.includeArchived) {
    params.set("include_archived", "true");
  }
  if (filters.limit) {
    params.set("limit", String(filters.limit));
  }
  if (filters.offset) {
    params.set("offset", String(filters.offset));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function createChatSession(
  payload: CreateChatSessionPayload
): Promise<ChatSession> {
  return requestJson<ChatSession>("/genai/chat-sessions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listChatSessions(
  filters: ChatSessionFilters = {},
  signal?: AbortSignal
): Promise<ChatSessionList> {
  return requestJson<ChatSessionList>(`/genai/chat-sessions${chatSessionQuery(filters)}`, {
    signal
  });
}

export async function getChatSession(
  sessionId: string,
  signal?: AbortSignal
): Promise<ChatSessionDetail> {
  return requestJson<ChatSessionDetail>(`/genai/chat-sessions/${sessionId}`, { signal });
}

export async function updateChatSession(
  sessionId: string,
  payload: UpdateChatSessionPayload
): Promise<ChatSession> {
  return requestJson<ChatSession>(`/genai/chat-sessions/${sessionId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function archiveChatSession(sessionId: string): Promise<ChatSession> {
  return requestJson<ChatSession>(`/genai/chat-sessions/${sessionId}/archive`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function sendChatMessage(
  sessionId: string,
  payload: SendChatMessagePayload
): Promise<SendChatMessageResponse> {
  return requestJson<SendChatMessageResponse>(`/genai/chat-sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listContextCustomers(signal?: AbortSignal): Promise<ContextOption[]> {
  return requestJson<ContextOption[]>("/genai/context/customers", { signal });
}

export async function listContextProjects(
  customerId?: string | null,
  signal?: AbortSignal
): Promise<ContextOption[]> {
  const params = new URLSearchParams();
  if (customerId) {
    params.set("customer_id", customerId);
  }
  const query = params.toString();
  return requestJson<ContextOption[]>(`/genai/context/projects${query ? `?${query}` : ""}`, {
    signal
  });
}
