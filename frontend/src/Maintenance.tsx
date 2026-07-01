import { useState } from "react";

import {
  deleteClientAndRelatedData,
  deleteProjectAndRelatedData,
  getDashboardFilterCacheStatus,
  getInScopeAssignmentGroupsStatus,
  importInScopeAssignmentGroups,
  prepareOperationalReprocessing,
  refreshDashboardFilterCache,
  resetProjectOperationalData,
} from "./api/admin";
import type {
  DashboardFilterCacheStatusItem,
  InScopeAssignmentGroupsImportResponse,
  InScopeAssignmentGroupsStatusResponse,
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
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [referenceStatus, setReferenceStatus] =
    useState<InScopeAssignmentGroupsStatusResponse | null>(null);
  const [referenceResult, setReferenceResult] =
    useState<InScopeAssignmentGroupsImportResponse | null>(null);
  const [isImportingReference, setIsImportingReference] = useState(false);
  const [isLoadingReferenceStatus, setIsLoadingReferenceStatus] = useState(false);
  const [referenceMessage, setReferenceMessage] = useState<string | null>(null);
  const [referenceError, setReferenceError] = useState<string | null>(null);
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
    setReferenceFile(null);
    setReferenceStatus(null);
    setReferenceResult(null);
    setReferenceMessage(null);
    setReferenceError(null);
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
      setReferenceFile(null);
      setReferenceStatus(null);
      setReferenceResult(null);
      setReferenceMessage(null);
      setReferenceError(null);
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

  async function refreshReferenceStatus(showMessage = true) {
    if (!projectId.trim()) {
      setReferenceError("Select a customer/project first.");
      return;
    }
    setIsLoadingReferenceStatus(true);
    setReferenceError(null);
    try {
      const status = await getInScopeAssignmentGroupsStatus(projectId.trim());
      setReferenceStatus(status);
      if (showMessage) {
        setReferenceMessage(
          `Reference status loaded. Active assignment groups: ${formatNumber(
            status.active_count
          )}.`
        );
      }
    } catch (requestError) {
      setReferenceError(
        maintenanceActionErrorMessage(
          requestError,
          "In-Scope Assignment Groups status"
        )
      );
    } finally {
      setIsLoadingReferenceStatus(false);
    }
  }

  async function handleImportReference() {
    if (!projectId.trim()) {
      setReferenceError("Select a customer/project first.");
      return;
    }
    if (!referenceFile) {
      setReferenceError("Choose the In-Scope Assignment Groups workbook first.");
      return;
    }
    setIsImportingReference(true);
    setReferenceError(null);
    setReferenceMessage(null);
    try {
      const result = await importInScopeAssignmentGroups(projectId.trim(), referenceFile);
      setReferenceResult(result);
      setReferenceMessage(
        `Import completed. ${formatNumber(
          result.imported_count
        )} active assignment groups are now loaded for this project. Next: prepare operational reprocessing below, then resume processing in Upload Center.`
      );
      await refreshReferenceStatus(false);
    } catch (requestError) {
      setReferenceError(
        maintenanceActionErrorMessage(
          requestError,
          "In-Scope Assignment Groups import"
        )
      );
    } finally {
      setIsImportingReference(false);
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
            <p className="label">Reference Data</p>
            <h2>In-Scope Assignment Groups Reference</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={!projectId.trim() || isLoadingReferenceStatus}
              onClick={() => void refreshReferenceStatus()}
            >
              {isLoadingReferenceStatus ? "Loading..." : "Show Reference Status"}
            </button>
          </div>
        </div>
        <div className="warning-list">
          <p>
            Import the workbook with columns <strong>Assigment Groups</strong> and{" "}
            <strong>Track</strong>. This replaces the active in-scope assignment group
            reference for the selected project and marks dashboard filter cache stale.
          </p>
          <p>
            Importing this reference does not reprocess uploaded ticket data. Use Operational
            Reprocessing below, then complete processing in Upload Center.
          </p>
        </div>
        <div className="form-grid summary-block">
          <label>
            <span>Reference workbook</span>
            <input
              type="file"
              accept=".xlsx,.csv"
              onChange={(event) => setReferenceFile(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            type="button"
            disabled={!projectId.trim() || !referenceFile || isImportingReference}
            onClick={() => void handleImportReference()}
          >
            {isImportingReference ? "Importing..." : "Import In-Scope Assignment Groups"}
          </button>
        </div>
        <div className="message-stack" role="status" aria-live="polite">
          {referenceMessage ? <p className="success-text">{referenceMessage}</p> : null}
          {referenceError ? <p className="error-text">{referenceError}</p> : null}
        </div>
        {referenceResult ? (
          <div className="summary-block">
            <p className="scope-note">
              Import succeeded for {referenceResult.source_filename}. The reference has been
              replaced for this project; no ticket data has been reprocessed yet.
            </p>
            <div className="summary-grid">
              <div>
                <p className="label">Imported</p>
                <strong>{formatNumber(referenceResult.imported_count)}</strong>
              </div>
              <div>
                <p className="label">Skipped Rows</p>
                <strong>{formatNumber(referenceResult.skipped_count)}</strong>
              </div>
              <div>
                <p className="label">Duplicate Rows</p>
                <strong>{formatNumber(referenceResult.duplicate_count)}</strong>
              </div>
              <div>
                <p className="label">Warnings</p>
                <strong>{formatNumber(referenceResult.warning_count)}</strong>
              </div>
            </div>
            {referenceResult.warnings.length > 0 ? (
              <ul className="warning-list">
                {referenceResult.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
            <p className="muted-text">
              Next step: use Operational Reprocessing below, then complete the required
              ingestion/normalization/apply mapping step in Upload Center.
            </p>
          </div>
        ) : null}
        {referenceStatus ? (
          <div className="summary-block">
            <p className="label">Active Reference Rows</p>
            <strong>{formatNumber(referenceStatus.active_count)}</strong>
            <p className="muted-text">
              Last imported: {referenceStatus.last_imported_at ?? "Not available"}
            </p>
            <div className="table-scroll">
              <table className="details-table">
                <thead>
                  <tr>
                    <th>Assignment Group</th>
                    <th>Track</th>
                    <th>Source Row</th>
                  </tr>
                </thead>
                <tbody>
                  {referenceStatus.preview_rows.length === 0 ? (
                    <tr>
                      <td colSpan={3}>No active reference rows found.</td>
                    </tr>
                  ) : (
                    referenceStatus.preview_rows.map((row) => (
                      <tr key={`${row.assignment_group}-${row.source_row_number ?? ""}`}>
                        <td>{row.assignment_group}</td>
                        <td>{row.functional_track ?? ""}</td>
                        <td>{row.source_row_number ?? ""}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
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
