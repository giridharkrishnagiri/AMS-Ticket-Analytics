import { useState } from "react";

const starterQuestions = [
  "How many applications are in the inventory?",
  "Show applications by functional track.",
  "Which parent applications have the highest active users?",
  "How many tickets were created in the latest complete 6 months?",
  "Which applications have the highest ticket volume?",
  "Show ticket distribution by SAP vs Non-SAP.",
  "What is the OLA summary?",
  "Plot applications by functional track.",
  "Create a bar chart of top applications by active users.",
  "Show ticket distribution by SAP vs Non-SAP as a pie chart.",
  "Create a line chart of monthly ticket volume.",
  "Plot top applications by ticket volume.",
  "Show OLA adherence by vendor as a bar chart."
];

type ChatInputProps = {
  disabled: boolean;
  isSending: boolean;
  onSend: (content: string) => Promise<void>;
};

export function ChatInput({ disabled, isSending, onSend }: ChatInputProps) {
  const [content, setContent] = useState("");

  async function sendContent(nextContent: string) {
    const trimmed = nextContent.trim();
    if (!trimmed || disabled || isSending) {
      return;
    }
    setContent("");
    await onSend(trimmed);
  }

  return (
    <section className="chat-input-area" aria-label="Message composer">
      <div className="starter-questions">
        {starterQuestions.map((question) => (
          <button
            key={question}
            type="button"
            className="starter-question"
            disabled={disabled || isSending}
            onClick={() => void sendContent(question)}
          >
            {question}
          </button>
        ))}
      </div>

      <label className="chat-input-label">
        <span>Message</span>
        <textarea
          value={content}
          rows={4}
          placeholder="Ask a governed aggregate or chart question about Applications, Tickets, or SLA / OLA."
          disabled={disabled || isSending}
          onChange={(event) => setContent(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void sendContent(content);
            }
          }}
        />
      </label>
      <div className="chat-input-actions">
        <span className="helper-text">Enter sends. Shift+Enter adds a new line.</span>
        <button
          type="button"
          className="primary-button"
          disabled={disabled || isSending || !content.trim()}
          onClick={() => void sendContent(content)}
        >
          {isSending ? "Sending..." : "Send"}
        </button>
      </div>
    </section>
  );
}
