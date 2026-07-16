import { useState } from "react";

import {
  deleteClientAndRelatedData,
  deleteProjectAndRelatedData,
  getDashboardFilterCacheStatus,
  listInScopeAssignmentGroups,
  prepareOperationalReprocessing,
  refreshDashboardFilterCache,
  resetProjectOperationalData,
  updateInScopeAssignmentGroups,
} from "./api/admin";
import type {
  DashboardFilterCacheStatusItem,
  InScopeAssignmentGroupRow,
  InScopeAssignmentGroupsUpdateResponse,
  OperationalDataResetResponse,
  OperationalReprocessingResponse,
} from "./api/admin";
import { getScopeSummary } from "./api/applicationInventory";
import type { ScopeSummary, ScopeSummaryValueCount } from "./api/applicationInventory";
import type { ProjectOption } from "./api/projects";
import CustomerSelector from "./CustomerSelector";

type ResetMode = "selected-data" | "project-data" | "customer-data";
type FilterCacheArea = "applications" | "volumetrics" | "all";
type ReprocessStartPoint =
  | "resume_from_ingestion"
  | "resume_from_normalization"
  | "reapply_mapping_only";
type ScopeDraftRow = InScopeAssignmentGroupRow & {
  original_functional_track: string | null;
  original_is_in_scope: boolean;
};

const selectedDataConfirmation = "RESET OPERATIONAL DATA";
const projectDataConfirmation = "RESET PROJECT DATA";
const customerDataConfirmation = "RESET CUSTOMER DATA";
const reprocessingConfirmation = "PREPARE REPROCESSING";

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

function formatReprocessDomainLabel(domain: string): string {
  const labels: Record<string, string> = {
    incidents: "Incidents",
    sc_tasks: "SC Tasks",
    problems: "Problems",
    changes: "Changes",
  };
  return labels[domain] ?? domain;
}

function formatReprocessStartPoint(startPoint: string): string {
  const labels: Record<string, string> = {
    resume_from_ingestion: "Resume from Ingestion",
    resume_from_normalization: "Resume from Normalization",
    reapply_mapping_only: "Reapply Mapping Only",
  };
  return labels[startPoint] ?? startPoint;
}

function nextStepForReprocessStartPoint(startPoint: string): string {
  if (startPoint === "resume_from_ingestion") {
    return "Next: go to Upload Center, run ingestion for the existing uploaded files, then normalize and apply mapping.";
  }
  if (startPoint === "resume_from_normalization") {
    return "Next: go to Upload Center, run normalization for the existing ingested files, then apply mapping.";
  }
  return "Next: go to Upload Center and apply the existing saved mapping for the selected files.";
}

function maintenanceActionErrorMessage(error: unknown, actionName: string): string {
  if (error instanceof Error) {
    if (error.message === "Not Found") {
      return `${actionName} is not available in the running backend. Restart the backend so the latest code is loaded, then try again.`;
    }
    return error.message;
  }
  return `${actionName} failed.`;
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
  const [scopeRows, setScopeRows] = useState<ScopeDraftRow[]>([]);
  const [scopeUpdateResult, setScopeUpdateResult] =
    useState<InScopeAssignmentGroupsUpdateResponse | null>(null);
  const [isLoadingScopeRows, setIsLoadingScopeRows] = useState(false);
  const [isApplyingScopeUpdates, setIsApplyingScopeUpdates] = useState(false);
  const [scopeMaintenanceMessage, setScopeMaintenanceMessage] = useState<string | null>(null);
  const [scopeMaintenanceError, setScopeMaintenanceError] = useState<string | null>(null);
  const [reprocessIncidents, setReprocessIncidents] = useState(false);
  const [reprocessScTasks, setReprocessScTasks] = useState(false);
  const [reprocessProblems, setReprocessProblems] = useState(false);
  const [reprocessChanges, setReprocessChanges] = useState(false);
  const [reprocessStartPoint, setReprocessStartPoint] =
    useState<ReprocessStartPoint>("resume_from_normalization");
  const [reprocessConfirmationText, setReprocessConfirmationText] = useState("");
  const [reprocessResult, setReprocessResult] =
    useState<OperationalReprocessingResponse | null>(null);
  const [isPreparingReprocess, setIsPreparingReprocess] = useState(false);
  const [reprocessMessage, setReprocessMessage] = useState<string | null>(null);
  const [reprocessError, setReprocessError] = useState<string | null>(null);
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
  const hasSelectedReprocessDomain =
    reprocessIncidents || reprocessScTasks || reprocessProblems || reprocessChanges;
  const canPrepareReprocessing =
    Boolean(projectId.trim()) &&
    hasSelectedReprocessDomain &&
    reprocessConfirmationText === reprocessingConfirmation &&
    !isPreparingReprocess;
  const changedScopeRows = scopeRows.filter(
    (row) =>
      (row.functional_track ?? "") !== (row.original_functional_track ?? "") ||
      row.is_in_scope !== row.original_is_in_scope
  );

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
    setScopeRows([]);
    setScopeUpdateResult(null);
    setScopeMaintenanceMessage(null);
    setScopeMaintenanceError(null);
    setReprocessIncidents(false);
    setReprocessScTasks(false);
    setReprocessProblems(false);
    setReprocessChanges(false);
    setReprocessStartPoint("resume_from_normalization");
    setReprocessConfirmationText("");
    setReprocessResult(null);
    setReprocessMessage(null);
    setReprocessError(null);
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
      setScopeRows([]);
      setScopeUpdateResult(null);
      setScopeMaintenanceMessage(null);
      setScopeMaintenanceError(null);
      setReprocessResult(null);
      setReprocessMessage(null);
      setReprocessError(null);
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

  async function refreshScopeRows(showMessage = true) {
    if (!projectId.trim()) {
      setScopeMaintenanceError("Select a customer/project first.");
      return;
    }
    setIsLoadingScopeRows(true);
    setScopeMaintenanceError(null);
    try {
      const rows = await listInScopeAssignmentGroups(projectId.trim(), 10000);
      setScopeRows(
        rows.map((row) => ({
          ...row,
          original_functional_track: row.functional_track,
          original_is_in_scope: row.is_in_scope,
        }))
      );
      setScopeUpdateResult(null);
      if (showMessage) {
        setScopeMaintenanceMessage(
          `Assignment group scope rows loaded: ${formatNumber(rows.length)}.`
        );
      }
    } catch (requestError) {
      setScopeMaintenanceError(
        maintenanceActionErrorMessage(requestError, "Assignment Group Scope list")
      );
    } finally {
      setIsLoadingScopeRows(false);
    }
  }

  function updateScopeDraftRow(
    rowId: string,
    patch: Partial<Pick<ScopeDraftRow, "functional_track" | "is_in_scope">>
  ) {
    setScopeRows((currentRows) =>
      currentRows.map((row) => (row.id === rowId ? { ...row, ...patch } : row))
    );
  }

  async function handleApplyScopeUpdates() {
    if (!projectId.trim()) {
      setScopeMaintenanceError("Select a customer/project first.");
      return;
    }
    if (changedScopeRows.length === 0) {
      setScopeMaintenanceError("No assignment group scope changes to apply.");
      return;
    }
    const confirmed = window.confirm(
      `Apply ${changedScopeRows.length} assignment group scope change(s) and update matching ticket rows?`
    );
    if (!confirmed) {
      return;
    }

    setIsApplyingScopeUpdates(true);
    setScopeMaintenanceError(null);
    setScopeMaintenanceMessage(null);
    try {
      const result = await updateInScopeAssignmentGroups(
        projectId.trim(),
        changedScopeRows.map((row) => ({
          id: row.id,
          functional_track: row.functional_track?.trim() || null,
          is_in_scope: row.is_in_scope,
        }))
      );
      setScopeUpdateResult(result);
      setScopeMaintenanceMessage(
        `Applied ${formatNumber(result.changed_count)} assignment group change(s). Updated ${formatNumber(
          result.tickets_updated_count
        )} ticket row(s) and ${formatNumber(result.inventory_rows_updated_count)} CMDB row(s).`
      );
      await refreshScopeRows(false);
      await refreshScopeSummary();
    } catch (requestError) {
      setScopeMaintenanceError(
        maintenanceActionErrorMessage(requestError, "Assignment Group Scope update")
      );
    } finally {
      setIsApplyingScopeUpdates(false);
    }
  }

  function selectedReprocessDomains() {
    const domains: string[] = [];
    if (reprocessIncidents) {
      domains.push("incidents");
    }
    if (reprocessScTasks) {
      domains.push("sc_tasks");
    }
    if (reprocessProblems) {
      domains.push("problems");
    }
    if (reprocessChanges) {
      domains.push("changes");
    }
    return domains;
  }

  async function handlePrepareReprocessing() {
    if (!projectId.trim()) {
      setReprocessError("Select a customer/project first.");
      return;
    }
    const domains = selectedReprocessDomains();
    if (domains.length === 0) {
      setReprocessError("Select at least one operational domain to prepare.");
      return;
    }
    if (reprocessConfirmationText !== reprocessingConfirmation) {
      setReprocessError(`Confirmation text must match exactly: ${reprocessingConfirmation}`);
      return;
    }
    const confirmed = window.confirm(
      "This will clear downstream outputs for the selected domains but preserve raw uploaded files. Continue?"
    );
    if (!confirmed) {
      return;
    }

    setIsPreparingReprocess(true);
    setReprocessError(null);
    setReprocessMessage(null);
    try {
      const result = await prepareOperationalReprocessing(
        projectId.trim(),
        domains,
        reprocessStartPoint,
        reprocessConfirmationText
      );
      setReprocessResult(result);
      setReprocessMessage(
        `Preparation completed for ${result.domains
          .map(formatReprocessDomainLabel)
          .join(", ")}. ${nextStepForReprocessStartPoint(result.start_point)}`
      );
      await refreshFilterCacheStatus();
    } catch (requestError) {
      setReprocessError(
        maintenanceActionErrorMessage(
          requestError,
          "Operational reprocessing preparation"
        )
      );
    } finally {
      setIsPreparingReprocess(false);
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
            <p className="label">Reference Data</p>
            <h2>Assignment Group Scope Maintenance</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={!projectId.trim() || isLoadingScopeRows}
              onClick={() => void refreshScopeRows()}
            >
              {isLoadingScopeRows ? "Loading..." : "Load Scope Rows"}
            </button>
            <button
              className="primary-button"
              type="button"
              disabled={
                !projectId.trim() || changedScopeRows.length === 0 || isApplyingScopeUpdates
              }
              onClick={() => void handleApplyScopeUpdates()}
            >
              {isApplyingScopeUpdates ? "Applying..." : "Save and Apply Scope Updates"}
            </button>
          </div>
        </div>
        <p className="scope-note">
          Functional Track is enriched from the assignment group scope reference during ticket
          scoping. Changes here update the reference row and only matching ticket rows for the
          changed assignment groups.
        </p>
        <div className="summary-grid summary-block">
          <div>
            <p className="label">Loaded Rows</p>
            <strong>{formatNumber(scopeRows.length)}</strong>
          </div>
          <div>
            <p className="label">Pending Changes</p>
            <strong>{formatNumber(changedScopeRows.length)}</strong>
          </div>
          <div>
            <p className="label">In Scope</p>
            <strong>{formatNumber(scopeRows.filter((row) => row.is_in_scope).length)}</strong>
          </div>
          <div>
            <p className="label">Out of Scope</p>
            <strong>{formatNumber(scopeRows.filter((row) => !row.is_in_scope).length)}</strong>
          </div>
        </div>
        <div className="message-stack" role="status" aria-live="polite">
          {scopeMaintenanceMessage ? (
            <p className="success-text">{scopeMaintenanceMessage}</p>
          ) : null}
          {scopeMaintenanceError ? <p className="error-text">{scopeMaintenanceError}</p> : null}
        </div>
        <div className="scroll-frame compact-file-frame">
          {scopeRows.length === 0 ? (
            <p className="muted-text">Load scope rows after selecting a customer/project.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Assignment Group</th>
                  <th>Functional Track</th>
                  <th>In Scope</th>
                  <th>Changed</th>
                </tr>
              </thead>
              <tbody>
                {scopeRows.map((row) => {
                  const changed =
                    (row.functional_track ?? "") !== (row.original_functional_track ?? "") ||
                    row.is_in_scope !== row.original_is_in_scope;
                  return (
                    <tr key={row.id}>
                      <td>{row.assignment_group}</td>
                      <td>
                        <input
                          type="text"
                          value={row.functional_track ?? ""}
                          onChange={(event) =>
                            updateScopeDraftRow(row.id, {
                              functional_track: event.target.value,
                            })
                          }
                        />
                      </td>
                      <td>
                        <select
                          value={row.is_in_scope ? "yes" : "no"}
                          onChange={(event) =>
                            updateScopeDraftRow(row.id, {
                              is_in_scope: event.target.value === "yes",
                            })
                          }
                        >
                          <option value="yes">Yes</option>
                          <option value="no">No</option>
                        </select>
                      </td>
                      <td>{changed ? "Yes" : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        {scopeUpdateResult ? (
          <div className="summary-block">
            <div className="summary-grid">
              <div>
                <p className="label">Changed Groups</p>
                <strong>{formatNumber(scopeUpdateResult.changed_count)}</strong>
              </div>
              <div>
                <p className="label">Tickets Updated</p>
                <strong>{formatNumber(scopeUpdateResult.tickets_updated_count)}</strong>
              </div>
              <div>
                <p className="label">CMDB Rows Updated</p>
                <strong>{formatNumber(scopeUpdateResult.inventory_rows_updated_count)}</strong>
              </div>
              <div>
                <p className="label">Unchanged Submitted</p>
                <strong>{formatNumber(scopeUpdateResult.unchanged_count)}</strong>
              </div>
            </div>
            {scopeUpdateResult.warnings.length > 0 ? (
              <ul className="warning-list">
                {scopeUpdateResult.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
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
            <p className="label">Operational Reprocessing</p>
            <h2>Prepare Existing Uploads for Resume</h2>
          </div>
        </div>
        <div className="warning-list">
          <p>
            This prepares selected domains for reprocessing and preserves raw uploaded files.
            It does not run ingestion, normalization, or apply mapping.
          </p>
          <p>
            After preparing, go to Upload Center and resume the needed processing step for the
            selected batches.
          </p>
        </div>
        <div className="summary-block">
          <p className="label">Domains</p>
          <div className="checkbox-grid">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={reprocessIncidents}
                onChange={(event) => setReprocessIncidents(event.target.checked)}
              />
              <span>Incidents</span>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={reprocessScTasks}
                onChange={(event) => setReprocessScTasks(event.target.checked)}
              />
              <span>SC Tasks</span>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={reprocessProblems}
                onChange={(event) => setReprocessProblems(event.target.checked)}
              />
              <span>Problems</span>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={reprocessChanges}
                onChange={(event) => setReprocessChanges(event.target.checked)}
              />
              <span>Changes</span>
            </label>
          </div>
        </div>
        <div className="form-grid summary-block">
          <label>
            <span>Restart point</span>
            <select
              value={reprocessStartPoint}
              onChange={(event) =>
                setReprocessStartPoint(event.target.value as ReprocessStartPoint)
              }
            >
              <option value="resume_from_ingestion">Resume from Ingestion</option>
              <option value="resume_from_normalization">Resume from Normalization</option>
              <option value="reapply_mapping_only">Reapply Mapping Only</option>
            </select>
            <span className="helper-text">
              The action clears only downstream stages needed for the selected restart point.
            </span>
          </label>
          <label>
            <span>Confirmation</span>
            <input
              value={reprocessConfirmationText}
              onChange={(event) => setReprocessConfirmationText(event.target.value)}
              placeholder={reprocessingConfirmation}
            />
            <span className="helper-text">Required text: {reprocessingConfirmation}</span>
          </label>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            type="button"
            disabled={!canPrepareReprocessing}
            onClick={() => void handlePrepareReprocessing()}
          >
            {isPreparingReprocess ? "Preparing..." : "Prepare Reprocessing"}
          </button>
        </div>
        <div className="message-stack" role="status" aria-live="polite">
          {reprocessMessage ? <p className="success-text">{reprocessMessage}</p> : null}
          {reprocessError ? <p className="error-text">{reprocessError}</p> : null}
        </div>
        {reprocessResult ? (
          <div className="summary-block">
            <p className="scope-note">
              Preparation succeeded for {reprocessResult.domains.map(formatReprocessDomainLabel).join(", ")}
              {" "}using {formatReprocessStartPoint(reprocessResult.start_point)}. This did not
              run ingestion, normalization, or apply mapping.
            </p>
            <div className="split-grid">
              <div>
                <p className="label">Cleared Row Counts</p>
                <div className="scroll-frame compact-file-frame">
                  <table>
                    <thead>
                      <tr>
                        <th>Table</th>
                        <th>Rows Cleared</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(reprocessResult.cleared_counts).map(([name, count]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>{formatNumber(count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <p className="label">Stage Status Updates</p>
                <div className="scroll-frame compact-file-frame">
                  <table>
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Rows Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(reprocessResult.updated_counts).map(([name, count]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>{formatNumber(count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <p className="muted-text">Preserved: {reprocessResult.preserved.join(", ")}</p>
            <p className="muted-text">{nextStepForReprocessStartPoint(reprocessResult.start_point)}</p>
            {reprocessResult.warnings.length > 0 ? (
              <ul className="warning-list">
                {reprocessResult.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
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
