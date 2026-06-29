import { useState } from "react";

import {
  deleteClientAndRelatedData,
  deleteProjectAndRelatedData,
  getDashboardFilterCacheStatus,
  refreshDashboardFilterCache,
  resetProjectOperationalData,
} from "./api/admin";
import type {
  DashboardFilterCacheStatusItem,
  OperationalDataResetResponse,
} from "./api/admin";
import { getScopeSummary } from "./api/applicationInventory";
import type { ScopeSummary, ScopeSummaryValueCount } from "./api/applicationInventory";
import type { ProjectOption } from "./api/projects";
import CustomerSelector from "./CustomerSelector";

type ResetMode = "selected-data" | "project-data" | "customer-data";
type FilterCacheArea = "applications" | "volumetrics" | "all";

const selectedDataConfirmation = "RESET OPERATIONAL DATA";
const projectDataConfirmation = "RESET PROJECT DATA";
const customerDataConfirmation = "RESET CUSTOMER DATA";

function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

function TopValues({ title, values }: { title: string; values: ScopeSummaryValueCount[] }) {
  return (
    <div className="summary-block">
      <p className="label">{title}</p>
      {values.length === 0 ? (
        <p className="muted-text">No out-of-scope values.</p>
      ) : (
        <div className="scroll-frame compact-file-frame">
          <table>
            <thead>
              <tr>
                <th>Value</th>
                <th>Tickets</th>
              </tr>
            </thead>
            <tbody>
              {values.map((row) => (
                <tr key={row.value}>
                  <td>{row.value}</td>
                  <td>{formatNumber(row.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function resultHasUpdates(result: OperationalDataResetResponse): boolean {
  return Object.keys(result.updated_counts ?? {}).length > 0;
}

function Maintenance() {
  const [projectId, setProjectId] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectOption | null>(null);
  const [resetMode, setResetMode] = useState<ResetMode>("selected-data");
  const [confirmation, setConfirmation] = useState("");
  const [resetIncidents, setResetIncidents] = useState(false);
  const [resetScTasks, setResetScTasks] = useState(false);
  const [resetProblems, setResetProblems] = useState(false);
  const [resetChanges, setResetChanges] = useState(false);
  const [resetIncidentSla, setResetIncidentSla] = useState(false);
  const [result, setResult] = useState<OperationalDataResetResponse | null>(null);
  const [scopeSummary, setScopeSummary] = useState<ScopeSummary | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingScope, setIsLoadingScope] = useState(false);
  const [isRefreshingCache, setIsRefreshingCache] = useState(false);
  const [cacheStatus, setCacheStatus] = useState<DashboardFilterCacheStatusItem[]>([]);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const requiredConfirmation =
    resetMode === "selected-data"
      ? selectedDataConfirmation
      : resetMode === "project-data"
        ? projectDataConfirmation
        : customerDataConfirmation;
  const hasSelectedResetCategory =
    resetIncidents || resetScTasks || resetProblems || resetChanges || resetIncidentSla;
  const canRun =
    Boolean(projectId.trim()) &&
    confirmation === requiredConfirmation &&
    !isRunning &&
    (resetMode !== "selected-data" || hasSelectedResetCategory);

  function clearMaintenanceForm() {
    setResetMode("selected-data");
    setConfirmation("");
    setResetIncidents(false);
    setResetScTasks(false);
    setResetProblems(false);
    setResetChanges(false);
    setResetIncidentSla(false);
    setResult(null);
    setScopeSummary(null);
    setCacheStatus([]);
    setCacheMessage(null);
    setMessage(null);
    setError(null);
  }

  function handleProjectIdChange(nextProjectId: string) {
    if (nextProjectId !== projectId) {
      setConfirmation("");
      setResult(null);
      setScopeSummary(null);
      setCacheStatus([]);
      setCacheMessage(null);
      setMessage(null);
      setError(null);
    }
    setProjectId(nextProjectId);
  }

  function handleModeChange(nextMode: ResetMode) {
    setResetMode(nextMode);
    setConfirmation("");
    setResult(null);
    setMessage(null);
    setError(null);
  }

  async function refreshScopeSummary() {
    if (!projectId.trim()) {
      setError("Select a customer/project first.");
      return;
    }

    setIsLoadingScope(true);
    setError(null);
    try {
      const summary = await getScopeSummary(projectId.trim());
      setScopeSummary(summary);
      setMessage("Scope summary refreshed.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load scope summary");
    } finally {
      setIsLoadingScope(false);
    }
  }

  async function refreshFilterCacheStatus() {
    if (!projectId.trim() || !selectedProject) {
      setError("Select a customer/project first.");
      return;
    }
    setError(null);
    try {
      const status = await getDashboardFilterCacheStatus(
        selectedProject.client_id,
        projectId.trim()
      );
      setCacheStatus(status.items);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load filter cache status"
      );
    }
  }

  async function handleRefreshFilterCache(area: FilterCacheArea) {
    if (!projectId.trim() || !selectedProject) {
      setError("Select a customer/project first.");
      return;
    }
    setIsRefreshingCache(true);
    setError(null);
    setCacheMessage(null);
    try {
      const response = await refreshDashboardFilterCache(
        selectedProject.client_id,
        projectId.trim(),
        area
      );
      setCacheMessage(
        `Filter cache refreshed for ${response.dashboard_area}. Facts: ${formatNumber(
          response.facts_count
        )}; catalog values: ${formatNumber(response.catalog_count)}; duration: ${formatNumber(
          response.duration_ms
        )} ms.`
      );
      await refreshFilterCacheStatus();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Filter cache refresh failed"
      );
    } finally {
      setIsRefreshingCache(false);
    }
  }

  async function handleRunReset() {
    if (!projectId.trim() || !selectedProject) {
      setError("Select a customer/project first.");
      return;
    }
    if (confirmation !== requiredConfirmation) {
      setError(`Confirmation text must match exactly: ${requiredConfirmation}`);
      return;
    }
    if (resetMode === "selected-data" && !hasSelectedResetCategory) {
      setError("Select at least one operational data category to reset.");
      return;
    }

    const actionDescription =
      resetMode === "selected-data"
        ? "clear the selected operational data categories for this project"
        : resetMode === "project-data"
          ? "remove the selected project and all related project data/configuration"
          : "remove the selected customer and all projects/configuration/data under it";
    const confirmed = window.confirm(`This will ${actionDescription}. Continue?`);
    if (!confirmed) {
      return;
    }

    setIsRunning(true);
    setError(null);
    setMessage(null);
    try {
      const nextResult =
        resetMode === "selected-data"
          ? await resetProjectOperationalData(projectId.trim(), confirmation, {
              resetIncidents,
              resetScTasks,
              resetProblems,
              resetChanges,
              resetIncidentSla,
            })
          : resetMode === "project-data"
            ? await deleteProjectAndRelatedData(projectId.trim(), confirmation)
            : await deleteClientAndRelatedData(selectedProject.client_id, confirmation);
      setResult(nextResult);
      setScopeSummary(null);
      setMessage("Maintenance reset completed.");
      if (resetMode !== "selected-data") {
        setProjectId("");
        setSelectedProject(null);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Maintenance reset failed");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section className="maintenance-layout" aria-labelledby="maintenance-heading">
      <div className="panel maintenance-panel">
        <div className="panel-heading">
          <div>
            <p className="label">Maintenance</p>
            <h2 id="maintenance-heading">Reset and Cleanup</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={clearMaintenanceForm}
            >
              Clear Maintenance Form
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void refreshScopeSummary()}
              disabled={!projectId.trim() || isLoadingScope}
            >
              {isLoadingScope ? "Refreshing..." : "Refresh Scope"}
            </button>
          </div>
        </div>

        <div className="form-grid">
          <CustomerSelector
            projectId={projectId}
            onProjectIdChange={handleProjectIdChange}
            onProjectChange={setSelectedProject}
          />
          <div className="info-card compact-info-card caution-card">
            <p className="label">Selected Context</p>
            <strong>{selectedProject?.customer_name ?? "No customer selected"}</strong>
            <span>{selectedProject?.name ?? "Choose a customer/project before resetting data."}</span>
          </div>
        </div>
      </div>

      <div className="panel maintenance-panel">
        <div className="panel-heading">
          <div>
            <p className="label">Dashboard Filter Cache</p>
            <h2>Refresh Static Filter Catalogs</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={!projectId.trim() || !selectedProject || isRefreshingCache}
              onClick={() => void refreshFilterCacheStatus()}
            >
              Show Cache Status
            </button>
          </div>
        </div>
        <div className="warning-list">
          <p>
            Refresh the filter cache after data uploads or maintenance resets if dashboard filters
            show stale counts. Dashboard dropdown values load from this catalog while dynamic counts
            update in the background.
          </p>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            type="button"
            disabled={!projectId.trim() || !selectedProject || isRefreshingCache}
            onClick={() => void handleRefreshFilterCache("applications")}
          >
            Refresh Applications Filter Cache
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={!projectId.trim() || !selectedProject || isRefreshingCache}
            onClick={() => void handleRefreshFilterCache("volumetrics")}
          >
            Refresh Volumetrics Filter Cache
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={!projectId.trim() || !selectedProject || isRefreshingCache}
            onClick={() => void handleRefreshFilterCache("all")}
          >
            {isRefreshingCache ? "Refreshing Filter Cache..." : "Refresh All Filter Caches"}
          </button>
        </div>
        {cacheStatus.length > 0 ? (
          <div className="table-scroll">
            <table className="details-table">
              <thead>
                <tr>
                  <th>Area</th>
                  <th>Status</th>
                  <th>Stale</th>
                  <th>Last Success</th>
                  <th>Data Version</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {cacheStatus.map((item) => (
                  <tr key={item.dashboard_area}>
                    <td>{item.dashboard_area}</td>
                    <td>{item.status}</td>
                    <td>{item.is_stale ? "Yes" : "No"}</td>
                    <td>{item.last_success_at ?? "Not available"}</td>
                    <td>{item.data_version ?? "Not available"}</td>
                    <td>{item.error_message ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {cacheMessage ? <p className="success-text">{cacheMessage}</p> : null}
      </div>

      <div className="panel maintenance-panel">
        <div className="panel-heading">
          <div>
            <p className="label">Reset Mode</p>
            <h2>Choose What to Reset</h2>
          </div>
        </div>

        <div className="reset-mode-grid" role="radiogroup" aria-label="Maintenance reset mode">
          <button
            className={resetMode === "selected-data" ? "reset-mode-card active" : "reset-mode-card"}
            type="button"
            onClick={() => handleModeChange("selected-data")}
          >
            <strong>Clear selected data reset</strong>
            <span>Reset Incidents, SC Tasks, Problems, Changes, and/or Incident SLA data.</span>
          </button>
          <button
            className={resetMode === "project-data" ? "reset-mode-card active" : "reset-mode-card"}
            type="button"
            onClick={() => handleModeChange("project-data")}
          >
            <strong>Project data reset</strong>
            <span>Remove the selected project and related project data/configuration.</span>
          </button>
          <button
            className={resetMode === "customer-data" ? "reset-mode-card active" : "reset-mode-card"}
            type="button"
            onClick={() => handleModeChange("customer-data")}
          >
            <strong>Entire customer data reset</strong>
            <span>Remove the customer and all related projects/configuration/data.</span>
          </button>
        </div>

        {resetMode === "selected-data" ? (
          <div className="summary-block">
            <p className="label">Operational Data Categories</p>
            <div className="checkbox-grid">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetIncidents}
                  onChange={(event) => setResetIncidents(event.target.checked)}
                />
                <span>Incidents</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetScTasks}
                  onChange={(event) => setResetScTasks(event.target.checked)}
                />
                <span>SC Tasks</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetProblems}
                  onChange={(event) => setResetProblems(event.target.checked)}
                />
                <span>Problems</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetChanges}
                  onChange={(event) => setResetChanges(event.target.checked)}
                />
                <span>Changes</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetIncidentSla}
                  onChange={(event) => setResetIncidentSla(event.target.checked)}
                />
                <span>Incident SLA</span>
              </label>
            </div>
            <div className="warning-list">
              <p>Application Inventory and mapping templates are preserved for selected data reset.</p>
              <p>Selecting Incidents also clears Incident SLA data to avoid stale enrichment values.</p>
            </div>
          </div>
        ) : resetMode === "project-data" ? (
          <div className="warning-list">
            <p>
              Project data reset removes the selected project and all related project data,
              including operational data, Application Inventory, and mapping templates.
            </p>
          </div>
        ) : (
          <div className="warning-list">
            <p>
              Entire customer data reset removes the selected customer/client and all
              projects/configuration/data under that customer.
            </p>
          </div>
        )}

        <div className="form-grid summary-block">
          <label>
            <span>Confirmation</span>
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={requiredConfirmation}
            />
            <span className="helper-text">Required text: {requiredConfirmation}</span>
          </label>
        </div>

        <div className="action-row">
          <button
            className="secondary-button danger-button"
            type="button"
            onClick={() => void handleRunReset()}
            disabled={!canRun}
          >
            {isRunning ? "Running..." : "Run Reset"}
          </button>
        </div>

        <div className="message-stack" role="status" aria-live="polite">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </div>

      {result ? (
        <div className="panel maintenance-panel">
          <div className="panel-heading">
            <div>
              <p className="label">Reset Result</p>
              <h2>Deleted and Updated Rows</h2>
            </div>
          </div>
          <div className="split-grid">
            <div>
              <p className="label">Deleted Row Counts</p>
              <div className="scroll-frame compact-file-frame summary-block">
                <table>
                  <thead>
                    <tr>
                      <th>Table</th>
                      <th>Rows Deleted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.deleted_counts).map(([tableName, count]) => (
                      <tr key={tableName}>
                        <td>{tableName}</td>
                        <td>{formatNumber(count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {resultHasUpdates(result) ? (
              <div>
                <p className="label">Updated Row Counts</p>
                <div className="scroll-frame compact-file-frame summary-block">
                  <table>
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Rows Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.updated_counts ?? {}).map(([categoryName, count]) => (
                        <tr key={categoryName}>
                          <td>{categoryName}</td>
                          <td>{formatNumber(count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
          <p className="muted-text summary-block">Preserved: {result.preserved.join(", ")}</p>
          {result.incident_sla_reset_reason ? (
            <p className="scope-note">{result.incident_sla_reset_reason}</p>
          ) : null}
        </div>
      ) : null}

      {scopeSummary ? (
        <div className="panel maintenance-panel">
          <div className="panel-heading">
            <div>
              <p className="label">Scope Summary</p>
              <h2>In-Scope vs Out-of-Scope Reconciliation</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">In-Scope Tickets</p>
              <strong>{formatNumber(scopeSummary.in_scope_tickets)}</strong>
            </div>
            <div>
              <p className="label">Out-of-Scope Tickets</p>
              <strong>{formatNumber(scopeSummary.out_of_scope_tickets)}</strong>
            </div>
            <div>
              <p className="label">In-Scope %</p>
              <strong>{formatPercent(scopeSummary.in_scope_pct)}</strong>
            </div>
            <div>
              <p className="label">Out-of-Scope %</p>
              <strong>{formatPercent(scopeSummary.out_of_scope_pct)}</strong>
            </div>
          </div>
          <div className="top-list-grid">
            <TopValues
              title="Top Out-of-Scope Assignment Groups"
              values={scopeSummary.top_out_of_scope_assignment_groups}
            />
            <TopValues
              title="Top Out-of-Scope Business Services"
              values={scopeSummary.top_out_of_scope_business_services}
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default Maintenance;
