import { useEffect, useMemo, useState } from "react";

import { listContextCustomers, listContextProjects } from "../api/chat";
import { executeGovernedTool, listToolCatalog, listToolRuns } from "../api/tools";
import type { ContextOption } from "../types/chat";
import type { ToolCatalogItem, ToolDomain, ToolExecuteResponse, ToolRun } from "../types/tools";

type MessageKind = "success" | "error" | "info";

type ToolFormState = {
  scope: "in_scope" | "out_of_scope" | "all";
  ticketType: "all" | "incident" | "sc_task";
  dimension: string;
  metric: string;
  topN: number;
  fromDate: string;
  toDate: string;
  dateGrain: "month" | "week";
  selectedPlan: string;
  agreementType: "ola" | "sla";
  advancedParameters: string;
};

const defaultForm: ToolFormState = {
  scope: "in_scope",
  ticketType: "all",
  dimension: "",
  metric: "",
  topN: 10,
  fromDate: "",
  toDate: "",
  dateGrain: "month",
  selectedPlan: "",
  agreementType: "ola",
  advancedParameters: "{}"
};

const examples: Array<{
  label: string;
  toolName: string;
  parameters: Partial<ToolFormState>;
}> = [
  {
    label: "Application Inventory Summary",
    toolName: "get_application_inventory_summary",
    parameters: {}
  },
  {
    label: "Applications by Functional Track",
    toolName: "get_application_distribution",
    parameters: { dimension: "functional_track", topN: 10 }
  },
  {
    label: "Criticality by Hosting Matrix",
    toolName: "get_application_criticality_hosting_matrix",
    parameters: {}
  },
  {
    label: "Lifecycle Planning Summary",
    toolName: "get_application_lifecycle_planning_summary",
    parameters: {}
  },
  {
    label: "Ticket Volume Summary",
    toolName: "get_ticket_volume_summary",
    parameters: { scope: "in_scope", ticketType: "all" }
  },
  {
    label: "Ticket Trend Summary",
    toolName: "get_ticket_trend_summary",
    parameters: { scope: "in_scope", ticketType: "all", dateGrain: "month" }
  },
  {
    label: "Top Applications by Ticket Volume",
    toolName: "get_top_applications_by_ticket_volume",
    parameters: { scope: "all", metric: "created_count", topN: 10 }
  },
  {
    label: "OLA Summary",
    toolName: "get_sla_ola_summary",
    parameters: { agreementType: "ola", metric: "both" }
  },
  {
    label: "SLA Summary",
    toolName: "get_sla_ola_summary",
    parameters: { agreementType: "sla", metric: "both" }
  }
];

function getErrorText(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function StatusMessage({ message, kind }: { message: string | null; kind: MessageKind }) {
  if (!message) {
    return null;
  }
  return <div className={`status-message status-${kind}`}>{message}</div>;
}

function buildParameters(tool: ToolCatalogItem | null, form: ToolFormState): Record<string, unknown> {
  const parameters: Record<string, unknown> = {};
  const toolName = tool?.tool_name ?? "";
  const domain = tool?.domain ?? "";

  if (domain === "tickets" || domain === "sla_ola") {
    parameters.scope = form.scope;
    parameters.ticket_type = form.ticketType;
  }
  if (domain === "sla_ola") {
    parameters.agreement_type = form.agreementType;
  }
  if (toolName === "get_ticket_trend_summary") {
    parameters.date_grain = form.dateGrain;
  }
  if (tool?.allowed_dimensions.length && form.dimension) {
    parameters.dimension = form.dimension;
  }
  if (tool?.allowed_metrics.length && form.metric) {
    parameters.metric = form.metric;
  }
  if (form.topN > 0) {
    parameters.top_n = form.topN;
  }
  if (form.fromDate) {
    parameters.from_date = form.fromDate;
  }
  if (form.toDate) {
    parameters.to_date = form.toDate;
  }
  if (toolName === "get_application_lifecycle_planning_summary" && form.selectedPlan) {
    parameters.selected_plan = form.selectedPlan;
  }

  return parameters;
}

function parseAdvancedParameters(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Advanced parameters must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

function ResultTable({ result }: { result: ToolExecuteResponse }) {
  if (result.rows.length === 0) {
    return <div className="empty-session-list">No result rows returned.</div>;
  }

  const columns =
    result.columns.length > 0
      ? result.columns
      : Object.keys(result.rows[0] ?? {}).map((key) => ({ key, label: key, type: "string" }));

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, rowIndex) => (
            <tr key={`${result.tool_name}-${rowIndex}`}>
              {columns.map((column) => (
                <td key={column.key}>{formatCell(row[column.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ToolRunsTable({ runs }: { runs: ToolRun[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Tool</th>
            <th>Domain</th>
            <th>Status</th>
            <th>Rows</th>
            <th>Duration ms</th>
            <th>Warnings</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>{formatDateTime(run.created_at)}</td>
              <td className="mono-text">{run.tool_name}</td>
              <td>{run.domain ?? "Not available"}</td>
              <td>
                <span className={`status-pill status-pill-${run.status}`}>{run.status}</span>
              </td>
              <td>{run.row_count ?? "Not available"}</td>
              <td>{run.execution_ms ?? "Not available"}</td>
              <td>{run.error_message ?? run.warnings_json?.join("; ") ?? ""}</td>
            </tr>
          ))}
          {runs.length === 0 ? (
            <tr>
              <td colSpan={7} className="empty-cell">
                No tool runs found.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

export function ToolsLabPage() {
  const [catalog, setCatalog] = useState<ToolCatalogItem[]>([]);
  const [selectedToolName, setSelectedToolName] = useState("");
  const [domainFilter, setDomainFilter] = useState("");
  const [customers, setCustomers] = useState<ContextOption[]>([]);
  const [projects, setProjects] = useState<ContextOption[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [form, setForm] = useState<ToolFormState>(defaultForm);
  const [result, setResult] = useState<ToolExecuteResponse | null>(null);
  const [runs, setRuns] = useState<ToolRun[]>([]);
  const [showJson, setShowJson] = useState(false);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<MessageKind>("info");

  const filteredCatalog = useMemo(() => {
    return domainFilter ? catalog.filter((tool) => tool.domain === domainFilter) : catalog;
  }, [catalog, domainFilter]);

  const selectedTool = useMemo(() => {
    return catalog.find((tool) => tool.tool_name === selectedToolName) ?? null;
  }, [catalog, selectedToolName]);

  async function loadCatalog() {
    setIsLoadingCatalog(true);
    setMessage(null);
    try {
      const response = await listToolCatalog();
      setCatalog(response.items);
      setSelectedToolName((current) => current || response.items[0]?.tool_name || "");
      setMessage("Tool catalog loaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsLoadingCatalog(false);
    }
  }

  async function loadRuns(toolName?: string) {
    try {
      const rows = await listToolRuns({ limit: 10, toolName });
      setRuns(rows);
    } catch {
      setRuns([]);
    }
  }

  useEffect(() => {
    void loadCatalog();
    void loadRuns();

    const controller = new AbortController();
    listContextCustomers(controller.signal)
      .then(setCustomers)
      .catch(() => setCustomers([]));
    listContextProjects(null, controller.signal)
      .then(setProjects)
      .catch(() => setProjects([]));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listContextProjects(customerId || null, controller.signal)
      .then((rows) => {
        setProjects(rows);
        if (projectId && !rows.some((row) => row.id === projectId)) {
          setProjectId("");
        }
      })
      .catch(() => setProjects([]));
    return () => controller.abort();
  }, [customerId, projectId]);

  function updateForm<K extends keyof ToolFormState>(key: K, value: ToolFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function chooseExample(toolName: string, parameters: Partial<ToolFormState>) {
    setSelectedToolName(toolName);
    setForm({ ...defaultForm, ...parameters });
    setResult(null);
    setMessage(`Example selected: ${toolName}`);
    setMessageKind("info");
  }

  async function executeSelectedTool() {
    if (!selectedTool) {
      setMessage("Select a governed tool before executing.");
      setMessageKind("error");
      return;
    }

    setIsExecuting(true);
    setMessage(null);
    try {
      const advanced = parseAdvancedParameters(form.advancedParameters);
      const parameters = { ...buildParameters(selectedTool, form), ...advanced };
      const response = await executeGovernedTool({
        tool_name: selectedTool.tool_name,
        customer_id: customerId || null,
        project_id: projectId || null,
        parameters,
        filters: {}
      });
      setResult(response);
      setMessage(
        response.status === "success"
          ? "Tool execution completed."
          : `Tool execution returned ${response.status}.`
      );
      setMessageKind(response.status === "success" ? "success" : "error");
      await loadRuns(selectedTool.tool_name);
    } catch (error) {
      setMessage(getErrorText(error));
      setMessageKind("error");
    } finally {
      setIsExecuting(false);
    }
  }

  const parameterPreview = selectedTool ? buildParameters(selectedTool, form) : {};

  return (
    <div className="tools-lab-layout">
      <aside className="tools-panel" aria-labelledby="tools-lab-controls-heading">
        <div className="section-heading compact-heading">
          <div>
            <p className="eyebrow">Phase 1D</p>
            <h2 id="tools-lab-controls-heading">Tools Lab</h2>
          </div>
          <button type="button" className="secondary-button" onClick={() => void loadCatalog()}>
            {isLoadingCatalog ? "Loading..." : "Refresh"}
          </button>
        </div>

        <p className="helper-text">
          Deterministic governed analytics tools run directly against approved backend logic. No LLM
          is used here.
        </p>

        <label>
          <span>Customer</span>
          <select value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
            <option value="">No customer selected</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Project</span>
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
            <option value="">No project selected</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Domain</span>
          <select value={domainFilter} onChange={(event) => setDomainFilter(event.target.value)}>
            <option value="">All domains</option>
            <option value="applications">Applications</option>
            <option value="tickets">Tickets</option>
            <option value="sla_ola">SLA / OLA</option>
          </select>
        </label>

        <label>
          <span>Governed tool</span>
          <select
            value={selectedToolName}
            onChange={(event) => {
              setSelectedToolName(event.target.value);
              setResult(null);
            }}
          >
            {filteredCatalog.map((tool) => (
              <option key={tool.tool_name} value={tool.tool_name}>
                {tool.display_name}
              </option>
            ))}
          </select>
        </label>

        <div className="tools-examples">
          {examples.map((example) => (
            <button
              key={example.label}
              type="button"
              className="starter-question"
              onClick={() => chooseExample(example.toolName, example.parameters)}
            >
              {example.label}
            </button>
          ))}
        </div>

        <div className="tool-parameters">
          <div className="parameter-grid">
            <label>
              <span>Scope</span>
              <select
                value={form.scope}
                onChange={(event) =>
                  updateForm("scope", event.target.value as ToolFormState["scope"])
                }
              >
                <option value="in_scope">in_scope</option>
                <option value="out_of_scope">out_of_scope</option>
                <option value="all">all</option>
              </select>
            </label>

            <label>
              <span>Ticket Type</span>
              <select
                value={form.ticketType}
                onChange={(event) =>
                  updateForm("ticketType", event.target.value as ToolFormState["ticketType"])
                }
              >
                <option value="all">all</option>
                <option value="incident">incident</option>
                <option value="sc_task">sc_task</option>
              </select>
            </label>

            <label>
              <span>Dimension</span>
              <select
                value={form.dimension}
                onChange={(event) => updateForm("dimension", event.target.value)}
              >
                <option value="">None</option>
                {selectedTool?.allowed_dimensions.map((dimension) => (
                  <option key={dimension} value={dimension}>
                    {dimension}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Metric</span>
              <select
                value={form.metric}
                onChange={(event) => updateForm("metric", event.target.value)}
              >
                <option value="">Default</option>
                {selectedTool?.allowed_metrics.map((metric) => (
                  <option key={metric} value={metric}>
                    {metric}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Top N</span>
              <input
                type="number"
                min="1"
                max="500"
                value={form.topN}
                onChange={(event) => updateForm("topN", Number(event.target.value))}
              />
            </label>

            <label>
              <span>Date Grain</span>
              <select
                value={form.dateGrain}
                onChange={(event) =>
                  updateForm("dateGrain", event.target.value as ToolFormState["dateGrain"])
                }
              >
                <option value="month">month</option>
                <option value="week">week</option>
              </select>
            </label>

            <label>
              <span>From Date</span>
              <input
                type="date"
                value={form.fromDate}
                onChange={(event) => updateForm("fromDate", event.target.value)}
              />
            </label>

            <label>
              <span>To Date</span>
              <input
                type="date"
                value={form.toDate}
                onChange={(event) => updateForm("toDate", event.target.value)}
              />
            </label>

            <label>
              <span>Agreement Type</span>
              <select
                value={form.agreementType}
                onChange={(event) =>
                  updateForm(
                    "agreementType",
                    event.target.value as ToolFormState["agreementType"]
                  )
                }
              >
                <option value="ola">OLA</option>
                <option value="sla">SLA</option>
              </select>
            </label>

            <label>
              <span>Selected Plan</span>
              <select
                value={form.selectedPlan}
                onChange={(event) => updateForm("selectedPlan", event.target.value)}
              >
                <option value="">None</option>
                <option value="Invest">Invest</option>
                <option value="Disinvest">Disinvest</option>
                <option value="Maintain">Maintain</option>
                <option value="Retired">Retired</option>
              </select>
            </label>
          </div>

          <label>
            <span>Advanced parameter overrides</span>
            <textarea
              value={form.advancedParameters}
              rows={5}
              onChange={(event) => updateForm("advancedParameters", event.target.value)}
            />
          </label>
        </div>

        <button
          type="button"
          className="primary-button"
          disabled={!selectedTool || isExecuting}
          onClick={() => void executeSelectedTool()}
        >
          {isExecuting ? "Executing..." : "Execute Tool"}
        </button>
      </aside>

      <section className="surface tools-result-panel" aria-labelledby="tools-lab-result-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Governed Result</p>
            <h2 id="tools-lab-result-heading">
              {selectedTool?.display_name ?? "Select a tool"}
            </h2>
            <p className="helper-text">{selectedTool?.description}</p>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setShowJson((current) => !current)}
          >
            {showJson ? "Hide JSON" : "Show JSON"}
          </button>
        </div>

        <StatusMessage message={message} kind={messageKind} />

        <dl className="tool-meta-grid">
          <div>
            <dt>Domain</dt>
            <dd>{selectedTool?.domain ?? "Not selected"}</dd>
          </div>
          <div>
            <dt>Safety Level</dt>
            <dd>{selectedTool?.data_safety_level ?? "Not selected"}</dd>
          </div>
          <div>
            <dt>Max Rows</dt>
            <dd>{selectedTool?.max_rows ?? "Not selected"}</dd>
          </div>
          <div>
            <dt>Parameters</dt>
            <dd className="mono-text">{JSON.stringify(parameterPreview)}</dd>
          </div>
        </dl>

        {result ? (
          <div className="tool-result-content">
            <div className="result-box">
              <strong>{result.summary.title}</strong>
              <p>{result.summary.description}</p>
              <dl className="metrics-list">
                <div>
                  <dt>Status</dt>
                  <dd>
                    <span className={`status-pill status-pill-${result.status}`}>
                      {result.status}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Rows</dt>
                  <dd>{result.row_count}</dd>
                </div>
                <div>
                  <dt>Truncated</dt>
                  <dd>{result.truncated ? "Yes" : "No"}</dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>{result.execution_ms ?? 0} ms</dd>
                </div>
              </dl>
            </div>

            {result.data_notes.length > 0 ? (
              <div className="note-list">
                <strong>Data notes</strong>
                <ul>
                  {result.data_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {result.warnings.length > 0 ? (
              <div className="warning-list">
                <strong>Warnings</strong>
                <ul>
                  {result.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <ResultTable result={result} />

            {showJson ? (
              <pre className="json-preview">{JSON.stringify(result, null, 2)}</pre>
            ) : null}
          </div>
        ) : (
          <div className="empty-thread">
            Select a tool and execute it to view compact governed aggregate results.
          </div>
        )}

        <div className="tool-runs-section">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">History</p>
              <h3>Recent Tool Runs</h3>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void loadRuns(selectedToolName || undefined)}
            >
              Refresh Runs
            </button>
          </div>
          <ToolRunsTable runs={runs} />
        </div>
      </section>
    </div>
  );
}
