import type { ChatMessage } from "../../types/chat";

type ChatThreadProps = {
  messages: ChatMessage[];
  isLoading: boolean;
};

type UsageMetadata = {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  estimated_cost?: number | null;
};

function metadataString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function metadataNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function usageMetadata(value: unknown): UsageMetadata {
  return value && typeof value === "object" ? (value as UsageMetadata) : {};
}

function roleLabel(role: string): string {
  if (role === "user") {
    return "You";
  }
  if (role === "assistant") {
    return "Assistant";
  }
  return role;
}

function assistantMetadata(message: ChatMessage) {
  if (message.role !== "assistant" && message.role !== "error") {
    return null;
  }
  const usage = usageMetadata(message.metadata.usage);
  const provider = metadataString(message.metadata.provider);
  const modelName = metadataString(message.metadata.model_name);
  const dataAccess = metadataString(message.metadata.data_access);
  const durationMs = metadataNumber(message.metadata.duration_ms);

  return (
    <dl className="message-metadata">
      <div>
        <dt>Model</dt>
        <dd>{modelName ? `${provider ?? "provider"} / ${modelName}` : "Not available"}</dd>
      </div>
      <div>
        <dt>Duration</dt>
        <dd>{durationMs !== null ? `${durationMs} ms` : "Not available"}</dd>
      </div>
      <div>
        <dt>Tokens</dt>
        <dd>
          {usage.prompt_tokens ?? 0} / {usage.completion_tokens ?? 0}
        </dd>
      </div>
      <div>
        <dt>Data access</dt>
        <dd>{dataAccess ?? "none_phase_1c"}</dd>
      </div>
    </dl>
  );
}

export function ChatThread({ messages, isLoading }: ChatThreadProps) {
  return (
    <section className="chat-thread" aria-live="polite" aria-label="Chat messages">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message chat-message-${message.role}`}>
          <div className="message-label">{roleLabel(message.role)}</div>
          <div className="message-bubble">
            {message.content.split("\n").map((line, index) => (
              <p key={`${message.id}-${index}`}>{line || " "}</p>
            ))}
            {assistantMetadata(message)}
          </div>
        </article>
      ))}

      {isLoading ? (
        <article className="chat-message chat-message-assistant">
          <div className="message-label">Assistant</div>
          <div className="message-bubble">
            <p>Thinking...</p>
          </div>
        </article>
      ) : null}

      {messages.length === 0 && !isLoading ? (
        <div className="empty-thread">
          Start a new Phase 1C chat. This workbench can discuss configuration and future GenAI
          capabilities, but it does not query live dashboard data yet.
        </div>
      ) : null}
    </section>
  );
}
