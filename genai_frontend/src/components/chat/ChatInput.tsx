import { useState } from "react";

const starterQuestions = [
  "What can this GenAI workbench do?",
  "What will data-aware Q&A support in the next phase?",
  "How will governed analytics tools protect dashboard data?",
  "Why should GenAI not write SQL directly?",
  "What kind of questions will I be able to ask about Applications and Tickets?"
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
          placeholder="Ask about the GenAI workbench setup or future governed analytics plans."
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
