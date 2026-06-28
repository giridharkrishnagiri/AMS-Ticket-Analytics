import type { ChatSession } from "../../types/chat";

type ChatSessionListProps = {
  sessions: ChatSession[];
  activeSessionId: string | null;
  includeArchived: boolean;
  isLoading: boolean;
  onNewChat: () => void;
  onRefresh: () => void;
  onSelectSession: (sessionId: string) => void;
  onArchiveSession: (sessionId: string) => void;
  onToggleArchived: (includeArchived: boolean) => void;
};

function formatSessionTime(value: string | null): string {
  if (!value) {
    return "No messages yet";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function sessionDomain(session: ChatSession): string {
  const domain = session.metadata.domain;
  return typeof domain === "string" ? domain : "General";
}

export function ChatSessionList({
  sessions,
  activeSessionId,
  includeArchived,
  isLoading,
  onNewChat,
  onRefresh,
  onSelectSession,
  onArchiveSession,
  onToggleArchived
}: ChatSessionListProps) {
  return (
    <aside className="chat-sessions" aria-label="Chat sessions">
      <div className="chat-sessions-header">
        <div>
          <p className="eyebrow">Sessions</p>
          <h2>Chats</h2>
        </div>
        <button type="button" className="primary-button" onClick={onNewChat}>
          New Chat
        </button>
      </div>

      <div className="session-tools">
        <button type="button" className="secondary-button" onClick={onRefresh}>
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
        <label className="checkbox-field archived-toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => onToggleArchived(event.target.checked)}
          />
          <span>Archived</span>
        </label>
      </div>

      <div className="session-list">
        {sessions.map((session) => (
          <article
            key={session.id}
            className={`session-list-item ${activeSessionId === session.id ? "active" : ""}`}
          >
            <button type="button" onClick={() => onSelectSession(session.id)}>
              <strong>{session.title}</strong>
              <span>{formatSessionTime(session.last_message_at)}</span>
              <small>
                {sessionDomain(session)}
                {session.is_archived ? " - archived" : ""}
              </small>
            </button>
            {!session.is_archived ? (
              <button
                type="button"
                className="link-button"
                onClick={() => onArchiveSession(session.id)}
              >
                Archive
              </button>
            ) : null}
          </article>
        ))}

        {sessions.length === 0 ? (
          <div className="empty-session-list">No chat sessions found.</div>
        ) : null}
      </div>
    </aside>
  );
}
