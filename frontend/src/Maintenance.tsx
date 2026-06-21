import { useState } from "react";

import {
  deleteClientAndRelatedData,
  deleteProjectAndRelatedData,
  resetOperationalData,
  resetProjectOperationalData,
} from "./api/admin";
import type { OperationalDataResetResponse } from "./api/admin";
import { getScopeSummary } from "./api/applicationInventory";
import type { ScopeSummary, ScopeSummaryValueCount } from "./api/applicationInventory";
import type { ProjectOption } from "./api/projects";
import CustomerSelector from "./CustomerSelector";

const globalRequiredConfirmation = "RESET OPERATIONAL DATA";
const deleteProjectConfirmation = "DELETE PROJECT";
const deleteClientConfirmation = "DELETE CLIENT";

type ScopedCleanupAction = "project-operational" | "delete-project" | "delete-client";

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
        <div className="table-wrap">
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

function Maintenance() {
  const [projectId, setProjectId] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectOption | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [scopedAction, setScopedAction] =
    useState<ScopedCleanupAction>("project-operational");
  const [scopedConfirmation, setScopedConfirmation] = useState("");
  const [resetIncidents, setResetIncidents] = useState(false);
  const [resetScTasks, setResetScTasks] = useState(false);
  const [resetIncidentSla, setResetIncidentSla] = useState(false);
  const [resetResult, setResetResult] = useState<OperationalDataResetResponse | null>(null);
  const [scopedResult, setScopedResult] = useState<OperationalDataResetResponse | null>(null);
  const [scopeSummary, setScopeSummary] = useState<ScopeSummary | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [isRunningScopedCleanup, setIsRunningScopedCleanup] = useState(false);
  const [isLoadingScope, setIsLoadingScope] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const requiredScopedConfirmation =
    scopedAction === "project-operational"
      ? globalRequiredConfirmation
      : scopedAction === "delete-project"
        ? deleteProjectConfirmation
        : deleteClientConfirmation;
  const hasSelectedResetCategory = resetIncidents || resetScTasks || resetIncidentSla;
  const canRunScopedCleanup =
    Boolean(projectId.trim()) &&
    scopedConfirmation === requiredScopedConfirmation &&
    !isRunningScopedCleanup &&
    (scopedAction !== "project-operational" || hasSelectedResetCategory);

  const selectedResetDescriptions = [
    resetIncidents
      ? "This will delete Incident tickets and related Incident raw/upload/job data for the selected project. Resetting Incidents will also reset Incident SLA data to prevent stale SLA rows."
      : null,
    resetScTasks
      ? "This will delete SC Task tickets and related SC Task raw/upload/job data for the selected project."
      : null,
    resetIncidentSla && !resetIncidents
      ? "This will delete only Incident SLA upload rows/history and clear SLA enrichment fields from Incident tickets. Incident and SC Task ticket records will remain."
      : null,
  ].filter((description): description is string => Boolean(description));

  async function handleReset() {
    if (confirmation !== globalRequiredConfirmation) {
      setError("Confirmation text must match exactly.");
      return;
    }

    const confirmed = window.confirm(
      "This will clear operational ticket, upload, raw row, and SLA data. Application Inventory, customers, projects, and mapping templates will be preserved."
    );
    if (!confirmed) {
      return;
    }

    setIsResetting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await resetOperationalData(confirmation);
      setResetResult(result);
      setMessage("Operational data reset completed.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Reset failed");
    } finally {
      setIsResetting(false);
    }
  }

  async function handleScopedCleanup() {
    if (!projectId.trim() || !selectedProject) {
      setError("Select a customer/project first.");
      return;
    }
    if (scopedAction === "project-operational" && !hasSelectedResetCategory) {
      setError("Select at least one operational data category to reset.");
      return;
    }
    if (scopedConfirmation !== requiredScopedConfirmation) {
      setError(`Confirmation text must match exactly: ${requiredScopedConfirmation}`);
      return;
    }

    const actionText =
      scopedAction === "project-operational"
        ? "clear operational data for the selected project while preserving Application Inventory and mapping templates"
        : scopedAction === "delete-project"
          ? "delete the selected project and all related data/configuration"
          : "delete the selected customer/client and all related projects/data/configuration";
    const confirmed = window.confirm(`This will ${actionText}. Continue?`);
    if (!confirmed) {
      return;
    }

    setIsRunningScopedCleanup(true);
    setError(null);
    setMessage(null);
    try {
      const result =
        scopedAction === "project-operational"
          ? await resetProjectOperationalData(projectId, scopedConfirmation, {
              resetIncidents,
              resetScTasks,
              resetIncidentSla,
            })
          : scopedAction === "delete-project"
            ? await deleteProjectAndRelatedData(projectId, scopedConfirmation)
            : await deleteClientAndRelatedData(selectedProject.client_id, scopedConfirmation);
      setScopedResult(result);
      setScopeSummary(null);
      setMessage("Selected maintenance action completed.");
      if (scopedAction !== "project-operational") {
        setProjectId("");
        setSelectedProject(null);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Maintenance action failed");
    } finally {
      setIsRunningScopedCleanup(false);
    }
  }

  async function refreshScopeSummary() {
    if (!projectId.trim()) {
      setError("Select a customer first.");
      return;
    }

    setIsLoadingScope(true);
    setError(null);
    try {
      const summary = await getScopeSummary(projectId);
      setScopeSummary(summary);
      setMessage("Scope summary refreshed.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load scope summary");
    } finally {
      setIsLoadingScope(false);
    }
  }

  return (
    <section className="upload-layout" aria-labelledby="maintenance-heading">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Maintenance</p>
            <h2 id="maintenance-heading">Operational Data Reset</h2>
          </div>
        </div>
        <p className="scope-note">
          Reset clears operational ticket/upload/SLA data and preserves Application Inventory,
          customers, projects, and mapping templates.
        </p>
        <div className="form-grid">
          <label>
            <span>Confirmation</span>
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={globalRequiredConfirmation}
            />
          </label>
        </div>
        <div className="action-row">
          <button
            className="secondary-button danger-button"
            type="button"
            onClick={() => void handleReset()}
            disabled={confirmation !== globalRequiredConfirmation || isResetting}
          >
            {isResetting ? "Resetting..." : "Reset Operational Data"}
          </button>
        </div>

        {resetResult ? (
          <div className="summary-block">
            <p className="label">Deleted Row Counts</p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Rows Deleted</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(resetResult.deleted_counts).map(([tableName, count]) => (
                    <tr key={tableName}>
                      <td>{tableName}</td>
                      <td>{formatNumber(count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted-text summary-block">
              Preserved: {resetResult.preserved.join(", ")}
            </p>
          </div>
        ) : null}
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Project / Customer Maintenance</p>
            <h2>Scoped Cleanup And Scope Summary</h2>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void refreshScopeSummary()}
            disabled={!projectId.trim() || isLoadingScope}
          >
            {isLoadingScope ? "Refreshing..." : "Refresh Scope"}
          </button>
        </div>
        <div className="form-grid">
          <CustomerSelector
            projectId={projectId}
            onProjectIdChange={setProjectId}
            onProjectChange={setSelectedProject}
          />
          <label>
            <span>Cleanup Action</span>
            <select
              value={scopedAction}
              onChange={(event) => {
                setScopedAction(event.target.value as ScopedCleanupAction);
                setScopedConfirmation("");
                setScopedResult(null);
                setResetIncidents(false);
                setResetScTasks(false);
                setResetIncidentSla(false);
              }}
            >
              <option value="project-operational">
                Clear selected project operational data only
              </option>
              <option value="delete-project">Delete selected project and all related data</option>
              <option value="delete-client">
                Delete selected customer/client and all related projects
              </option>
            </select>
          </label>
          <label>
            <span>Scoped Confirmation</span>
            <input
              value={scopedConfirmation}
              onChange={(event) => setScopedConfirmation(event.target.value)}
              placeholder={requiredScopedConfirmation}
            />
            <span className="helper-text">
              Required text: {requiredScopedConfirmation}
            </span>
          </label>
        </div>
        {scopedAction === "project-operational" ? (
          <div className="summary-block">
            <p className="label">Operational Data Categories</p>
            <div className="checkbox-grid">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetIncidents}
                  onChange={(event) => setResetIncidents(event.target.checked)}
                />
                <span>Reset all Incidents</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetScTasks}
                  onChange={(event) => setResetScTasks(event.target.checked)}
                />
                <span>Reset all SC Tasks</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={resetIncidentSla}
                  onChange={(event) => setResetIncidentSla(event.target.checked)}
                />
                <span>Reset all Incident SLA data</span>
              </label>
            </div>
            <div className="warning-list">
              {selectedResetDescriptions.length === 0 ? (
                <p>Select at least one category. Nothing will be reset until a category is selected.</p>
              ) : (
                selectedResetDescriptions.map((description) => (
                  <p key={description}>{description}</p>
                ))
              )}
            </div>
          </div>
        ) : null}
        <div className="action-row summary-block">
          <button
            className="secondary-button danger-button"
            type="button"
            onClick={() => void handleScopedCleanup()}
            disabled={!canRunScopedCleanup}
          >
            {isRunningScopedCleanup ? "Running..." : "Run Selected Cleanup"}
          </button>
        </div>
        <p className="scope-note">
          Project operational cleanup preserves the selected project, customer, Application
          Inventory, and mapping templates. Project/client delete removes configuration too.
        </p>
        {scopedResult ? (
          <div className="summary-block">
            <p className="label">Scoped Deleted Row Counts</p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Rows Deleted</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(scopedResult.deleted_counts).map(([tableName, count]) => (
                    <tr key={tableName}>
                      <td>{tableName}</td>
                      <td>{formatNumber(count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted-text summary-block">
              Preserved: {scopedResult.preserved.join(", ")}
            </p>
            {Object.keys(scopedResult.updated_counts ?? {}).length > 0 ? (
              <>
                <p className="label summary-block">Updated Row Counts</p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Rows Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(scopedResult.updated_counts ?? {}).map(
                        ([categoryName, count]) => (
                          <tr key={categoryName}>
                            <td>{categoryName}</td>
                            <td>{formatNumber(count)}</td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
            {scopedResult.incident_sla_reset_reason ? (
              <p className="scope-note">{scopedResult.incident_sla_reset_reason}</p>
            ) : null}
          </div>
        ) : null}
        {scopeSummary ? (
          <>
            <div className="summary-grid summary-block">
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
            <TopValues
              title="Top Out-of-Scope Assignment Groups"
              values={scopeSummary.top_out_of_scope_assignment_groups}
            />
            <TopValues
              title="Top Out-of-Scope Business Services"
              values={scopeSummary.top_out_of_scope_business_services}
            />
          </>
        ) : (
          <p className="muted-text summary-block">Refresh scope to view classified ticket counts.</p>
        )}
      </div>

      <div className="message-stack">
        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </section>
  );
}

export default Maintenance;
