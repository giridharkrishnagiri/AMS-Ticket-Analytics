export type ChatDomain =
  | "General"
  | "Applications"
  | "Tickets"
  | "SLA / OLA"
  | "Problems / Changes"
  | "Dashboard";

export type ContextOption = {
  id: string;
  name: string;
  code: string;
  customer_id: string | null;
  customer_name: string | null;
  customer_code: string | null;
  label: string;
};

export type ChatContext = {
  customer_id: string | null;
  project_id: string | null;
  domain: ChatDomain;
  page: string;
  filters: Record<string, unknown>;
  time_range: Record<string, unknown>;
};

export type ChatSession = {
  id: string;
  customer_id: string | null;
  project_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  is_archived: boolean;
  metadata: Record<string, unknown>;
};

export type ChatSessionList = {
  items: ChatSession[];
  total: number;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system" | "error" | string;
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type ChatSessionDetail = {
  session: ChatSession;
  messages: ChatMessage[];
};

export type CreateChatSessionPayload = {
  customer_id: string | null;
  project_id: string | null;
  title?: string;
  metadata: Record<string, unknown>;
};

export type UpdateChatSessionPayload = {
  title?: string;
  metadata?: Record<string, unknown>;
};

export type SendChatMessagePayload = {
  content: string;
  context: ChatContext;
};

export type SendChatMessageResponse = {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  session: {
    id: string;
    title: string;
    last_message_at: string | null;
  };
};
