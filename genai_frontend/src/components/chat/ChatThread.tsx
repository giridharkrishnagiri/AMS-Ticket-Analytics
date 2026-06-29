import type { ChatMessage } from "../../types/chat";

type ChatThreadProps = {
  messages: ChatMessage[];
  isLoading: boolean;
  onOpenChart: (chartId: string) => void;
};

type UsageMetadata = {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  estimated_cost?: number | null;
};

type ToolColumn = {
  key: string;
  label: string;
  type?: string;
};

type ToolResult = {
  tool_name?: string;
  domain?: string;
  status?: string;
  summary?: {
    title?: string;
    description?: string | null;
  };
  columns?: ToolColumn[];
  rows?: Record<string, unknown>[];
  applied_filters?: Record<string, unknown>;
  row_count?: number;
  truncated?: boolean;
};

type GeneratedChartMetadata = {
  chart_id: string;
  title: string;
  chart_type: string;
  chart_library: string;
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

function stringArrayMetadata(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item : String(item)))
    .filter((item) => item.trim());
}

function toolResultsMetadata(value: unknown): ToolResult[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is ToolResult => Boolean(item && typeof item === "object"));
}

function generatedChartsMetadata(value: unknown): GeneratedChartMetadata[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is GeneratedChartMetadata => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const candidate = item as Record<string, unknown>;
    return (
      typeof candidate.chart_id === "string" &&
      typeof candidate.title === "string" &&
      typeof candidate.chart_type === "string"
    );
  });
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
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

function MetadataList({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <details className="message-detail-section">
      <summary>{title}</summary>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </details>
  );
}

function CompactResults({ results }: { results: ToolResult[] }) {
  if (results.length === 0) {
    return null;
  }
  return (
    <details className="message-detail-section">
      <summary>Compact Results</summary>
      <div className="compact-results">
        {results.map((result) => {
          const columns = result.columns ?? [];
          const rows = result.rows ?? [];
          const displayRows = rows.slice(0, 12);
          return (
            <section key={`${result.tool_name}-${result.status}`} className="compact-result">
              <div className="compact-result-heading">
                <strong>{result.summary?.title ?? result.tool_name ?? "Tool result"}</strong>
                <span>
                  {result.status ?? "unknown"} · {result.row_count ?? rows.length} rows
                  {result.truncated ? " · truncated" : ""}
                </span>
              </div>
              {columns.length > 0 && displayRows.length > 0 ? (
                <div className="compact-table-scroll">
                  <table className="compact-result-table">
                    <thead>
                      <tr>
                        {columns.map((column) => (
                          <th key={column.key}>{column.label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {displayRows.map((row, rowIndex) => (
                        <tr key={`${result.tool_name}-${rowIndex}`}>
                          {columns.map((column) => (
                            <td key={column.key}>{formatCellValue(row[column.key])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted-inline">No compact rows returned.</p>
              )}
            </section>
          );
        })}
      </div>
    </details>
  );
}

function GeneratedCharts({
  charts,
  onOpenChart
}: {
  charts: GeneratedChartMetadata[];
  onOpenChart: (chartId: string) => void;
}) {
  if (charts.length === 0) {
    return null;
  }
  return (
    <div className="generated-chart-cards">
      {charts.map((chart) => (
        <div key={chart.chart_id} className="generated-chart-card">
          <div>
            <strong>{chart.title}</strong>
            <span>
              {chart.chart_type.replace("_", " ")} / {chart.chart_library || "plotly"}
            </span>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={() => onOpenChart(chart.chart_id)}
          >
            Open chart in AI Charts
          </button>
        </div>
      ))}
    </div>
  );
}

function assistantMetadata(message: ChatMessage, onOpenChart: (chartId: string) => void) {
  if (message.role !== "assistant" && message.role !== "error") {
    return null;
  }
  const usage = usageMetadata(message.metadata.usage);
  const provider = metadataString(message.metadata.provider);
  const modelName = metadataString(message.metadata.model_name);
  const dataAccess = metadataString(message.metadata.data_access);
  const durationMs = metadataNumber(message.metadata.duration_ms);
  const toolsUsed = stringArrayMetadata(message.metadata.tools_used);
  const dataNotes = stringArrayMetadata(message.metadata.data_notes);
  const warnings = stringArrayMetadata(message.metadata.warnings);
  const assumptions = stringArrayMetadata(message.metadata.assumptions);
  const toolResults = toolResultsMetadata(message.metadata.tool_results);
  const generatedCharts = generatedChartsMetadata(message.metadata.generated_charts);

  return (
    <>
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
          <dd>{dataAccess ?? "none_general"}</dd>
        </div>
      </dl>
      <GeneratedCharts charts={generatedCharts} onOpenChart={onOpenChart} />
      <div className="message-details">
        <MetadataList title="Tools Used" values={toolsUsed} />
        <MetadataList title="Data Notes" values={dataNotes} />
        <MetadataList title="Warnings" values={warnings} />
        <MetadataList title="Assumptions" values={assumptions} />
        <CompactResults results={toolResults} />
      </div>
    </>
  );
}

export function ChatThread({ messages, isLoading, onOpenChart }: ChatThreadProps) {
  return (
    <section className="chat-thread" aria-live="polite" aria-label="Chat messages">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message chat-message-${message.role}`}>
          <div className="message-label">{roleLabel(message.role)}</div>
          <div className="message-bubble">
            {message.content.split("\n").map((line, index) => (
              <p key={`${message.id}-${index}`}>{line || " "}</p>
            ))}
            {assistantMetadata(message, onOpenChart)}
          </div>
        </article>
      ))}

      {isLoading ? (
        <article className="chat-message chat-message-assistant">
          <div className="message-label">Assistant</div>
          <div className="message-bubble">
            <p>Thinking...</p>
            <p>Planning governed analytics tools...</p>
            <p>Executing approved analytics tools...</p>
            <p>Summarizing answer...</p>
          </div>
        </article>
      ) : null}

      {messages.length === 0 && !isLoading ? (
        <div className="empty-thread">
          Start a Phase 2A chat. This workbench answers supported data questions through approved
          governed analytics tools and can generate governed Plotly charts from those results.
        </div>
      ) : null}
    </section>
  );
}
