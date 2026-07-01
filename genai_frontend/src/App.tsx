import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getBackendHealth,
  getGenAIConfig,
  getGenAISafetySettings,
  listGenAIPrompts,
  listGenAIUsageLogs,
  reseedGenAIPrompts,
  resetGenAIPrompt,
  testGenAIConnection,
  updateGenAIConfig,
  updateGenAIPrompt,
  updateGenAISafetySettings
} from "./api/genai";
import { AIChartsPage } from "./pages/AIChartsPage";
import { ChatPage } from "./pages/ChatPage";
import { ToolsLabPage } from "./pages/ToolsLabPage";
import type {
  BackendHealth,
  GenAIConfig,
  GenAIConfigUpdate,
  GenAIProvider,
  GenAIPromptTemplate,
  GenAIResponseStyle,
  GenAISafetySettings,
  GenAISafetySettingsUpdate,
  GenAITestResponse,
  GenAIUsageLog
} from "./types/genai";

type AppView = "chat" | "tools" | "charts" | "admin" | "usage";
type AdminTab = "config" | "prompts" | "safety";
type MessageKind = "success" | "error" | "info";
type HealthState = "unchecked" | "checking" | "healthy" | "degraded" | "offline";

const providerOptions: GenAIProvider[] = ["openai", "azure", "anthropic", "ollama", "custom"];
const responseStyleOptions: GenAIResponseStyle[] = ["concise", "standard", "detailed"];

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function configToUpdate(config: GenAIConfig): GenAIConfigUpdate {
  return {
    is_enabled: config.is_enabled,
    provider: config.provider,
    model_name: config.model_name ?? "",
    temperature: config.temperature,
    top_p: config.top_p,
    max_output_tokens: config.max_output_tokens,
    timeout_seconds: config.timeout_seconds,
    max_tool_calls: config.max_tool_calls,
    allow_recommendations: config.allow_recommendations,
    allow_chart_generation: config.allow_chart_generation,
    response_style: config.response_style
  };
}

function safetyToUpdate(settings: GenAISafetySettings): GenAISafetySettingsUpdate {
  return {
    allow_application_detail_rows: settings.allow_application_detail_rows,
    allow_ticket_detail_rows: settings.allow_ticket_detail_rows,
    allow_aggregate_ticket_data: settings.allow_aggregate_ticket_data,
    allow_problem_change_data: settings.allow_problem_change_data,
    allow_sla_ola_aggregate_data: settings.allow_sla_ola_aggregate_data,
    max_rows_returned_to_llm: settings.max_rows_returned_to_llm,
    max_chart_data_points: settings.max_chart_data_points,
    enforce_complete_month_cutoff: settings.enforce_complete_month_cutoff,
    mask_sensitive_fields: settings.mask_sensitive_fields
  };
}

function getErrorText(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error";
}

function StatusMessage({
  message,
  kind
}: {
  message: string | null;
  kind: MessageKind;
}) {
  if (!message) {
    return null;
  }
  return <div className={`status-message status-${kind}`}>{message}</div>;
}

function PagePlaceholder({ title, text }: { title: string; text: string }) {
  return (
    <section className="surface placeholder-surface" aria-labelledby={`${title}-heading`}>
      <p className="eyebrow">MVP Placeholder</p>
      <h2 id={`${title}-heading`}>{title}</h2>
      <p>{text}</p>
    </section>
  );
}

function ConfigPanel() {
  const [form, setForm] = useState<GenAIConfigUpdate | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<MessageKind>("info");
  const [testResult, setTestResult] = useState<GenAITestResponse | null>(null);

  async function loadConfig() {
    setIsLoading(true);
    setMessage(null);
    try {
      const config = await getGenAIConfig();
      setForm(configToUpdate(config));
      setMessage("Configuration loaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadConfig();
  }, []);

  function updateField<K extends keyof GenAIConfigUpdate>(key: K, value: GenAIConfigUpdate[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  async function saveConfig() {
    if (!form) {
      return;
    }
    setIsSaving(true);
    setMessage(null);
    try {
      const saved = await updateGenAIConfig(form);
      setForm(configToUpdate(saved));
      setMessage("Configuration saved.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsSaving(false);
    }
  }

  async function testConnection() {
    setIsTesting(true);
    setTestResult(null);
    setMessage(null);
    try {
      const result = await testGenAIConnection();
      setTestResult(result);
      setMessage(result.ok ? "LLM connection succeeded." : result.error_message);
      setMessageKind(result.ok ? "success" : "error");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsTesting(false);
    }
  }

  if (isLoading && !form) {
    return <p className="loading-text">Loading configuration...</p>;
  }

  return (
    <section className="surface" aria-labelledby="ai-config-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Admin</p>
          <h2 id="ai-config-heading">AI Configuration</h2>
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={() => void loadConfig()}>
            Refresh
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!form || isSaving}
            onClick={() => void saveConfig()}
          >
            {isSaving ? "Saving..." : "Save Configuration"}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!form || isTesting}
            onClick={() => void testConnection()}
          >
            {isTesting ? "Testing..." : "Test LLM Connection"}
          </button>
        </div>
      </div>

      <p className="helper-text">
        API keys are read from backend environment variables and are not stored in this screen.
      </p>
      <StatusMessage message={message} kind={messageKind} />

      {form ? (
        <div className="form-grid">
          <label className="checkbox-field wide-field">
            <input
              type="checkbox"
              checked={form.is_enabled}
              onChange={(event) => updateField("is_enabled", event.target.checked)}
            />
            <span>Enable GenAI feature</span>
          </label>

          <label>
            <span>Provider</span>
            <select
              value={form.provider}
              onChange={(event) =>
                updateField("provider", event.target.value as GenAIProvider)
              }
            >
              {providerOptions.map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Model name</span>
            <input
              type="text"
              value={form.model_name ?? ""}
              onChange={(event) => updateField("model_name", event.target.value)}
              placeholder="gpt-4.1-mini"
            />
          </label>

          <label>
            <span>Temperature</span>
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={form.temperature}
              onChange={(event) => updateField("temperature", Number(event.target.value))}
            />
          </label>

          <label>
            <span>Top-p</span>
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={form.top_p}
              onChange={(event) => updateField("top_p", Number(event.target.value))}
            />
          </label>

          <label>
            <span>Max output tokens</span>
            <input
              type="number"
              min="100"
              max="8000"
              value={form.max_output_tokens}
              onChange={(event) => updateField("max_output_tokens", Number(event.target.value))}
            />
          </label>

          <label>
            <span>Timeout seconds</span>
            <input
              type="number"
              min="5"
              max="300"
              value={form.timeout_seconds}
              onChange={(event) => updateField("timeout_seconds", Number(event.target.value))}
            />
          </label>

          <label>
            <span>Max tool calls</span>
            <input
              type="number"
              min="0"
              max="50"
              value={form.max_tool_calls}
              onChange={(event) => updateField("max_tool_calls", Number(event.target.value))}
            />
          </label>

          <label>
            <span>Response style</span>
            <select
              value={form.response_style}
              onChange={(event) =>
                updateField("response_style", event.target.value as GenAIResponseStyle)
              }
            >
              {responseStyleOptions.map((style) => (
                <option key={style} value={style}>
                  {style}
                </option>
              ))}
            </select>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_recommendations}
              onChange={(event) => updateField("allow_recommendations", event.target.checked)}
            />
            <span>Allow recommendations</span>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_chart_generation}
              onChange={(event) => updateField("allow_chart_generation", event.target.checked)}
            />
            <span>Allow chart generation</span>
          </label>
        </div>
      ) : null}

      {testResult ? (
        <div className="result-box">
          <strong>{testResult.ok ? "Success" : "Setup check failed"}</strong>
          <p>{testResult.response_text ?? testResult.error_message}</p>
          <dl className="metrics-list">
            <div>
              <dt>Provider</dt>
              <dd>{testResult.provider}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{testResult.model_name ?? "Not configured"}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{testResult.duration_ms ?? 0} ms</dd>
            </div>
            <div>
              <dt>Tokens</dt>
              <dd>
                {(testResult.usage?.prompt_tokens ?? 0).toLocaleString()} prompt /{" "}
                {(testResult.usage?.completion_tokens ?? 0).toLocaleString()} completion
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
    </section>
  );
}

function PromptsPanel() {
  const [prompts, setPrompts] = useState<GenAIPromptTemplate[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<GenAIPromptTemplate | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");
  const [isCustomEnabled, setIsCustomEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<MessageKind>("info");

  async function loadPrompts() {
    setIsLoading(true);
    setMessage(null);
    try {
      const rows = await listGenAIPrompts();
      setPrompts(rows);
      setMessage("Prompt templates loaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadPrompts();
  }, []);

  function beginEdit(prompt: GenAIPromptTemplate) {
    setSelectedPrompt(prompt);
    setCustomPrompt(prompt.custom_prompt ?? "");
    setIsCustomEnabled(prompt.is_custom_enabled);
  }

  function replacePrompt(updated: GenAIPromptTemplate) {
    setPrompts((current) =>
      current.map((prompt) => (prompt.prompt_key === updated.prompt_key ? updated : prompt))
    );
    setSelectedPrompt(updated);
    setCustomPrompt(updated.custom_prompt ?? "");
    setIsCustomEnabled(updated.is_custom_enabled);
  }

  async function savePrompt() {
    if (!selectedPrompt) {
      return;
    }
    setMessage(null);
    try {
      const updated = await updateGenAIPrompt(selectedPrompt.prompt_key, {
        custom_prompt: customPrompt,
        is_custom_enabled: isCustomEnabled
      });
      replacePrompt(updated);
      setMessage("Prompt override saved.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    }
  }

  async function resetPrompt(promptKey: string) {
    setMessage(null);
    try {
      const updated = await resetGenAIPrompt(promptKey);
      replacePrompt(updated);
      setMessage("Prompt reset to default.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    }
  }

  async function reseedPrompts() {
    setMessage(null);
    try {
      const result = await reseedGenAIPrompts();
      await loadPrompts();
      setMessage(`Reseed complete. ${result.prompt_count} prompt templates are available.`);
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    }
  }

  return (
    <section className="surface" aria-labelledby="ai-prompts-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Admin</p>
          <h2 id="ai-prompts-heading">AI Prompts</h2>
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={() => void loadPrompts()}>
            Refresh
          </button>
          <button type="button" className="primary-button" onClick={() => void reseedPrompts()}>
            Reseed Default Prompts
          </button>
        </div>
      </div>

      <StatusMessage message={message} kind={messageKind} />

      {isLoading ? <p className="loading-text">Loading prompts...</p> : null}

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Prompt Key</th>
              <th>Display Name</th>
              <th>Description</th>
              <th>Custom Enabled</th>
              <th>Version</th>
              <th>Updated At</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr key={prompt.prompt_key}>
                <td className="mono-text">{prompt.prompt_key}</td>
                <td>{prompt.display_name}</td>
                <td>{prompt.description}</td>
                <td>{prompt.is_custom_enabled ? "Yes" : "No"}</td>
                <td>{prompt.version}</td>
                <td>{formatDateTime(prompt.updated_at)}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" onClick={() => beginEdit(prompt)}>
                      Edit
                    </button>
                    <button type="button" onClick={() => void resetPrompt(prompt.prompt_key)}>
                      Reset
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedPrompt ? (
        <div className="edit-panel" aria-labelledby="prompt-editor-heading">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">Prompt Editor</p>
              <h3 id="prompt-editor-heading">{selectedPrompt.display_name}</h3>
            </div>
            <button type="button" className="secondary-button" onClick={() => setSelectedPrompt(null)}>
              Cancel
            </button>
          </div>

          <label>
            <span>Default prompt</span>
            <textarea readOnly value={selectedPrompt.default_prompt} rows={8} />
          </label>

          <label>
            <span>Custom prompt</span>
            <textarea
              value={customPrompt}
              rows={8}
              onChange={(event) => setCustomPrompt(event.target.value)}
            />
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={isCustomEnabled}
              onChange={(event) => setIsCustomEnabled(event.target.checked)}
            />
            <span>Enable custom prompt</span>
          </label>

          <div className="button-row">
            <button type="button" className="primary-button" onClick={() => void savePrompt()}>
              Save
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void resetPrompt(selectedPrompt.prompt_key)}
            >
              Reset to default
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function SafetyPanel() {
  const [form, setForm] = useState<GenAISafetySettingsUpdate | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<MessageKind>("info");

  async function loadSafety() {
    setIsLoading(true);
    setMessage(null);
    try {
      const settings = await getGenAISafetySettings();
      setForm(safetyToUpdate(settings));
      setMessage("Safety settings loaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadSafety();
  }, []);

  function updateField<K extends keyof GenAISafetySettingsUpdate>(
    key: K,
    value: GenAISafetySettingsUpdate[K]
  ) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  async function saveSafety() {
    if (!form) {
      return;
    }
    setIsSaving(true);
    setMessage(null);
    try {
      const saved = await updateGenAISafetySettings(form);
      setForm(safetyToUpdate(saved));
      setMessage("Safety settings saved.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading && !form) {
    return <p className="loading-text">Loading safety settings...</p>;
  }

  return (
    <section className="surface" aria-labelledby="safety-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Admin</p>
          <h2 id="safety-heading">Safety &amp; Data Access</h2>
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={() => void loadSafety()}>
            Refresh
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!form || isSaving}
            onClick={() => void saveSafety()}
          >
            {isSaving ? "Saving..." : "Save Safety Settings"}
          </button>
        </div>
      </div>

      <p className="helper-text">
        Ticket detail rows should remain disabled unless explicitly required. GenAI should use
        aggregate ticket data by default.
      </p>
      <StatusMessage message={message} kind={messageKind} />

      {form ? (
        <div className="form-grid">
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_application_detail_rows}
              onChange={(event) =>
                updateField("allow_application_detail_rows", event.target.checked)
              }
            />
            <span>Allow application detail rows</span>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_ticket_detail_rows}
              onChange={(event) => updateField("allow_ticket_detail_rows", event.target.checked)}
            />
            <span>Allow ticket detail rows</span>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_aggregate_ticket_data}
              onChange={(event) =>
                updateField("allow_aggregate_ticket_data", event.target.checked)
              }
            />
            <span>Allow aggregate ticket data</span>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_problem_change_data}
              onChange={(event) => updateField("allow_problem_change_data", event.target.checked)}
            />
            <span>Allow Problem/Change data</span>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_sla_ola_aggregate_data}
              onChange={(event) =>
                updateField("allow_sla_ola_aggregate_data", event.target.checked)
              }
            />
            <span>Allow SLA/OLA aggregate data</span>
          </label>

          <label>
            <span>Max rows returned to LLM</span>
            <input
              type="number"
              min="1"
              max="10000"
              value={form.max_rows_returned_to_llm}
              onChange={(event) =>
                updateField("max_rows_returned_to_llm", Number(event.target.value))
              }
            />
          </label>

          <label>
            <span>Max chart data points</span>
            <input
              type="number"
              min="1"
              max="10000"
              value={form.max_chart_data_points}
              onChange={(event) =>
                updateField("max_chart_data_points", Number(event.target.value))
              }
            />
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.enforce_complete_month_cutoff}
              onChange={(event) =>
                updateField("enforce_complete_month_cutoff", event.target.checked)
              }
            />
            <span>Enforce complete-month cutoff</span>
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.mask_sensitive_fields}
              onChange={(event) => updateField("mask_sensitive_fields", event.target.checked)}
            />
            <span>Mask sensitive fields</span>
          </label>
        </div>
      ) : null}
    </section>
  );
}

function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("config");

  return (
    <div className="admin-layout">
      <nav className="sub-tabs" aria-label="Admin sections">
        <button
          type="button"
          className={activeTab === "config" ? "active" : ""}
          onClick={() => setActiveTab("config")}
        >
          AI Configuration
        </button>
        <button
          type="button"
          className={activeTab === "prompts" ? "active" : ""}
          onClick={() => setActiveTab("prompts")}
        >
          AI Prompts
        </button>
        <button
          type="button"
          className={activeTab === "safety" ? "active" : ""}
          onClick={() => setActiveTab("safety")}
        >
          Safety &amp; Data Access
        </button>
      </nav>

      {activeTab === "config" ? <ConfigPanel /> : null}
      {activeTab === "prompts" ? <PromptsPanel /> : null}
      {activeTab === "safety" ? <SafetyPanel /> : null}
    </div>
  );
}

function UsageLogsPage() {
  const [logs, setLogs] = useState<GenAIUsageLog[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [operationFilter, setOperationFilter] = useState("");
  const [limit, setLimit] = useState(50);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<MessageKind>("info");

  async function loadLogs() {
    setIsLoading(true);
    setMessage(null);
    try {
      const rows = await listGenAIUsageLogs({
        status: statusFilter || undefined,
        operation: operationFilter || undefined,
        limit
      });
      setLogs(rows);
      setMessage("Usage logs loaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadLogs();
  }, []);

  return (
    <section className="surface" aria-labelledby="usage-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Operations</p>
          <h2 id="usage-heading">Usage Logs</h2>
        </div>
        <button type="button" className="primary-button" onClick={() => void loadLogs()}>
          {isLoading ? "Loading..." : "Refresh"}
        </button>
      </div>

      <div className="filter-row">
        <label>
          <span>Status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All</option>
            <option value="success">success</option>
            <option value="error">error</option>
            <option value="disabled">disabled</option>
          </select>
        </label>
        <label>
          <span>Operation</span>
          <select
            value={operationFilter}
            onChange={(event) => setOperationFilter(event.target.value)}
          >
            <option value="">All</option>
            <option value="config_test">config_test</option>
            <option value="prompt_test">prompt_test</option>
            <option value="chat">chat</option>
            <option value="chat_agent">chat_agent</option>
            <option value="tool_execution">tool_execution</option>
            <option value="chart_generation">chart_generation</option>
            <option value="chart_update">chart_update</option>
            <option value="chart_duplicate">chart_duplicate</option>
            <option value="chart_archive">chart_archive</option>
            <option value="chart_reset">chart_reset</option>
          </select>
        </label>
        <label>
          <span>Limit</span>
          <input
            type="number"
            min="1"
            max="200"
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
          />
        </label>
      </div>

      <StatusMessage message={message} kind={messageKind} />

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Operation</th>
              <th>Provider</th>
              <th>Model</th>
              <th>Status</th>
              <th>Duration ms</th>
              <th>Prompt Tokens</th>
              <th>Completion Tokens</th>
              <th>Estimated Cost</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{formatDateTime(log.created_at)}</td>
                <td className="mono-text">{log.operation}</td>
                <td>{log.provider ?? "Not available"}</td>
                <td>{log.model_name ?? "Not available"}</td>
                <td>
                  <span className={`status-pill status-pill-${log.status}`}>{log.status}</span>
                </td>
                <td>{log.duration_ms ?? "Not available"}</td>
                <td>{log.prompt_tokens ?? "Not available"}</td>
                <td>{log.completion_tokens ?? "Not available"}</td>
                <td>{log.estimated_cost ?? "Not available"}</td>
                <td>{log.error_message ?? ""}</td>
              </tr>
            ))}
            {logs.length === 0 ? (
              <tr>
                <td colSpan={10} className="empty-cell">
                  No usage logs found.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function App() {
  const [activeView, setActiveView] = useState<AppView>("admin");
  const [selectedChartId, setSelectedChartId] = useState<string | null>(null);
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  const runHealthCheck = useCallback(async () => {
    const controller = new AbortController();
    setIsCheckingHealth(true);
    try {
      const nextHealth = await getBackendHealth(controller.signal);
      setHealth(nextHealth);
      setHealthError(null);
    } catch (error) {
      setHealth(null);
      setHealthError(getErrorText(error));
    } finally {
      setIsCheckingHealth(false);
    }
  }, []);

  const healthState: HealthState = useMemo(() => {
    if (isCheckingHealth) {
      return "checking";
    }
    if (health?.status?.toLowerCase() === "ok") {
      return "healthy";
    }
    if (health) {
      return health.status.toLowerCase() === "error" ? "offline" : "degraded";
    }
    return healthError ? "offline" : "unchecked";
  }, [health, healthError, isCheckingHealth]);

  const healthLabel = useMemo(() => {
    if (healthState === "healthy") {
      return "Healthy";
    }
    if (healthState === "degraded") {
      return "Degraded";
    }
    if (healthState === "offline") {
      return "Offline";
    }
    return healthState === "checking" ? "Checking" : "Check health";
  }, [healthState]);

  return (
    <main className="app-shell">
      <header className="top-header">
        <div>
          <p className="eyebrow">Experimental GenAI Workspace</p>
          <h1>AMS GenAI Analytics Workbench</h1>
        </div>
        <button
          type="button"
          className={`health-indicator health-${healthState}`}
          disabled={isCheckingHealth}
          title={healthError ?? "Run backend, database, lock, and frontend health diagnostics"}
          onClick={() => void runHealthCheck()}
        >
          <span aria-hidden="true" />
          <strong>Backend</strong>
          {healthLabel}
        </button>
      </header>

      <div className="notice-banner">
        This is a separate experimental GenAI workbench. The existing AMS Applications &amp;
        Volumetrics Analytics dashboard is unchanged.
      </div>

      <nav className="main-tabs" aria-label="Workbench sections">
        <button
          type="button"
          className={activeView === "chat" ? "active" : ""}
          onClick={() => setActiveView("chat")}
        >
          Chat
        </button>
        <button
          type="button"
          className={activeView === "tools" ? "active" : ""}
          onClick={() => setActiveView("tools")}
        >
          Tools Lab
        </button>
        <button
          type="button"
          className={activeView === "charts" ? "active" : ""}
          onClick={() => setActiveView("charts")}
        >
          AI Charts
        </button>
        <button
          type="button"
          className={activeView === "admin" ? "active" : ""}
          onClick={() => setActiveView("admin")}
        >
          Admin
        </button>
        <button
          type="button"
          className={activeView === "usage" ? "active" : ""}
          onClick={() => setActiveView("usage")}
        >
          Usage Logs
        </button>
      </nav>

      {activeView === "chat" ? (
        <ChatPage
          onOpenChart={(chartId) => {
            setSelectedChartId(chartId);
            setActiveView("charts");
          }}
        />
      ) : null}
      {activeView === "tools" ? <ToolsLabPage /> : null}
      {activeView === "charts" ? (
        <AIChartsPage
          selectedChartId={selectedChartId}
          onSelectedChartChange={setSelectedChartId}
        />
      ) : null}
      {activeView === "admin" ? <AdminPage /> : null}
      {activeView === "usage" ? <UsageLogsPage /> : null}
    </main>
  );
}

export default App;
