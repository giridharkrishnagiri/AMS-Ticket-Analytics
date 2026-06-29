import { useEffect, useState } from "react";

import {
  archiveChatSession,
  createChatSession,
  getChatSession,
  listChatSessions,
  listContextCustomers,
  listContextProjects,
  sendChatMessage
} from "../api/chat";
import { ChatInput } from "../components/chat/ChatInput";
import { ChatSessionList } from "../components/chat/ChatSessionList";
import { ChatThread } from "../components/chat/ChatThread";
import { ContextSelector } from "../components/chat/ContextSelector";
import type { ChatContext, ChatSession, ChatSessionDetail, ContextOption } from "../types/chat";

function defaultContext(): ChatContext {
  return {
    customer_id: null,
    project_id: null,
    domain: "General",
    page: "Chat",
    filters: {},
    time_range: {}
  };
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error";
}

export function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null);
  const [context, setContext] = useState<ChatContext>(() => defaultContext());
  const [customers, setCustomers] = useState<ContextOption[]>([]);
  const [projects, setProjects] = useState<ContextOption[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isLoadingContext, setIsLoadingContext] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error" | "info">("info");
  const [contextError, setContextError] = useState<string | null>(null);

  async function loadSessions(nextIncludeArchived = includeArchived) {
    setIsLoadingSessions(true);
    try {
      const result = await listChatSessions({ includeArchived: nextIncludeArchived, limit: 50 });
      setSessions(result.items);
    } catch (error) {
      setMessage(errorText(error));
      setMessageKind("error");
    } finally {
      setIsLoadingSessions(false);
    }
  }

  async function loadSession(sessionId: string) {
    setIsLoadingDetail(true);
    try {
      const nextDetail = await getChatSession(sessionId);
      setDetail(nextDetail);
      setActiveSessionId(sessionId);
      setMessage(null);
    } catch (error) {
      setMessage(errorText(error));
      setMessageKind("error");
    } finally {
      setIsLoadingDetail(false);
    }
  }

  async function loadContextOptions(customerId: string | null) {
    setIsLoadingContext(true);
    setContextError(null);
    try {
      const [customerRows, projectRows] = await Promise.all([
        listContextCustomers(),
        listContextProjects(customerId)
      ]);
      setCustomers(customerRows);
      setProjects(projectRows);
    } catch (error) {
      setContextError(errorText(error));
    } finally {
      setIsLoadingContext(false);
    }
  }

  useEffect(() => {
    void loadSessions(false);
    void loadContextOptions(null);
  }, []);

  useEffect(() => {
    void loadContextOptions(context.customer_id);
  }, [context.customer_id]);

  async function startNewChat(): Promise<string> {
    const session = await createChatSession({
      customer_id: context.customer_id,
      project_id: context.project_id,
      title: "New chat",
      metadata: { domain: context.domain }
    });
    setActiveSessionId(session.id);
    setDetail({ session, messages: [] });
    await loadSessions(includeArchived);
    return session.id;
  }

  async function handleNewChat() {
    setMessage(null);
    try {
      await startNewChat();
      setMessage("New chat session created.");
      setMessageKind("success");
    } catch (error) {
      setMessage(errorText(error));
      setMessageKind("error");
    }
  }

  async function handleSend(content: string) {
    setIsSending(true);
    setMessage(null);
    try {
      const sessionId = activeSessionId ?? (await startNewChat());
      await sendChatMessage(sessionId, { content, context });
      await loadSession(sessionId);
      await loadSessions(includeArchived);
    } catch (error) {
      setMessage(errorText(error));
      setMessageKind("error");
    } finally {
      setIsSending(false);
    }
  }

  async function handleArchive(sessionId: string) {
    setMessage(null);
    try {
      await archiveChatSession(sessionId);
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setDetail(null);
      }
      await loadSessions(includeArchived);
      setMessage("Chat session archived.");
      setMessageKind("success");
    } catch (error) {
      setMessage(errorText(error));
      setMessageKind("error");
    }
  }

  function handleContextChange(nextContext: ChatContext) {
    setContext(nextContext);
  }

  return (
    <div className="chat-layout">
      <ChatSessionList
        sessions={sessions}
        activeSessionId={activeSessionId}
        includeArchived={includeArchived}
        isLoading={isLoadingSessions}
        onNewChat={() => void handleNewChat()}
        onRefresh={() => void loadSessions(includeArchived)}
        onSelectSession={(sessionId) => void loadSession(sessionId)}
        onArchiveSession={(sessionId) => void handleArchive(sessionId)}
        onToggleArchived={(nextIncludeArchived) => {
          setIncludeArchived(nextIncludeArchived);
          void loadSessions(nextIncludeArchived);
        }}
      />

      <section className="surface chat-workspace" aria-labelledby="chat-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Phase 1E</p>
            <h2 id="chat-heading">{detail?.session.title ?? "Chat"}</h2>
          </div>
          <div className="button-row">
            {activeSessionId ? (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setActiveSessionId(null);
                  setDetail(null);
                  setMessage("Chat session closed.");
                  setMessageKind("info");
                }}
              >
                Close Session
              </button>
            ) : null}
          </div>
        </div>

        <ContextSelector
          context={context}
          customers={customers}
          projects={projects}
          isLoading={isLoadingContext}
          error={contextError}
          onChange={handleContextChange}
        />

        {message ? <div className={`status-message status-${messageKind}`}>{message}</div> : null}

        <ChatThread messages={detail?.messages ?? []} isLoading={isLoadingDetail || isSending} />

        <ChatInput
          disabled={detail?.session.is_archived ?? false}
          isSending={isSending}
          onSend={handleSend}
        />
      </section>
    </div>
  );
}
