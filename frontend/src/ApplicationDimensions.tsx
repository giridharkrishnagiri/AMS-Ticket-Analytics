import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  createApplicationDimension,
  deactivateApplicationDimension,
  enrichApplicationDimensions,
  getApplicationDimensionSummary,
  listApplicationDimensions,
  updateApplicationDimension,
  uploadApplicationDimensionsCsv,
} from "./api/applicationDimensions";
import type {
  ApplicationDimension,
  ApplicationDimensionPayload,
  BulkUploadResponse,
  EnrichmentSummary,
  ValueCount,
} from "./api/applicationDimensions";

type DimensionFormState = {
  customer_name: string;
  tower_name: string;
  cluster_name: string;
  application_group_name: string;
  application_name: string;
  application_alias: string;
  business_service_alias: string;
  cmdb_ci_alias: string;
  notes: string;
  is_active: boolean;
};

const emptyForm: DimensionFormState = {
  customer_name: "",
  tower_name: "",
  cluster_name: "",
  application_group_name: "",
  application_name: "",
  application_alias: "",
  business_service_alias: "",
  cmdb_ci_alias: "",
  notes: "",
  is_active: true,
};

function cleanOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function formToPayload(projectId: string, form: DimensionFormState): ApplicationDimensionPayload {
  return {
    project_id: projectId.trim(),
    customer_name: cleanOptional(form.customer_name),
    tower_name: cleanOptional(form.tower_name),
    cluster_name: cleanOptional(form.cluster_name),
    application_group_name: cleanOptional(form.application_group_name),
    application_name: form.application_name.trim(),
    application_alias: cleanOptional(form.application_alias),
    business_service_alias: cleanOptional(form.business_service_alias),
    cmdb_ci_alias: cleanOptional(form.cmdb_ci_alias),
    notes: cleanOptional(form.notes),
    is_active: form.is_active,
  };
}

function dimensionToForm(dimension: ApplicationDimension): DimensionFormState {
  return {
    customer_name: dimension.customer_name ?? "",
    tower_name: dimension.tower_name ?? "",
    cluster_name: dimension.cluster_name ?? "",
    application_group_name: dimension.application_group_name ?? "",
    application_name: dimension.application_name,
    application_alias: dimension.application_alias ?? "",
    business_service_alias: dimension.business_service_alias ?? "",
    cmdb_ci_alias: dimension.cmdb_ci_alias ?? "",
    notes: dimension.notes ?? "",
    is_active: dimension.is_active,
  };
}

function TopValues({ title, values }: { title: string; values: ValueCount[] }) {
  return (
    <div className="summary-block">
      <p className="label">{title}</p>
      {values.length === 0 ? (
        <p className="muted-text">No unmatched values.</p>
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

function ApplicationDimensions() {
  const [projectId, setProjectId] = useState("");
  const [dimensions, setDimensions] = useState<ApplicationDimension[]>([]);
  const [form, setForm] = useState<DimensionFormState>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [bulkResult, setBulkResult] = useState<BulkUploadResponse | null>(null);
  const [summary, setSummary] = useState<EnrichmentSummary | null>(null);
  const [isLoadingDimensions, setIsLoadingDimensions] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeCount = useMemo(
    () => dimensions.filter((dimension) => dimension.is_active).length,
    [dimensions]
  );

  async function refreshDimensions(nextProjectId = projectId) {
    if (!nextProjectId.trim()) {
      setError("Project ID is required.");
      return;
    }

    setIsLoadingDimensions(true);
    setError(null);
    try {
      const [nextDimensions, nextSummary] = await Promise.all([
        listApplicationDimensions(nextProjectId),
        getApplicationDimensionSummary(nextProjectId),
      ]);
      setDimensions(nextDimensions);
      setSummary(nextSummary);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load dimensions"
      );
    } finally {
      setIsLoadingDimensions(false);
    }
  }

  useEffect(() => {
    if (projectId.trim()) {
      void refreshDimensions(projectId);
    }
  }, []);

  function updateFormField(field: keyof DimensionFormState, value: string | boolean) {
    setForm((currentForm) => ({ ...currentForm, [field]: value }));
  }

  function handleCsvSelection(event: ChangeEvent<HTMLInputElement>) {
    setCsvFile(event.target.files?.[0] ?? null);
  }

  function clearForm() {
    setEditingId(null);
    setForm(emptyForm);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }
    if (!form.application_name.trim()) {
      setError("Application name is required.");
      return;
    }

    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const payload = formToPayload(projectId, form);
      if (editingId) {
        await updateApplicationDimension(editingId, payload);
        setMessage("Application dimension updated.");
      } else {
        await createApplicationDimension(payload);
        setMessage("Application dimension created.");
      }
      clearForm();
      await refreshDimensions(projectId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save mapping");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleBulkUpload() {
    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }
    if (!csvFile) {
      setError("Select a CSV file first.");
      return;
    }

    setIsUploading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await uploadApplicationDimensionsCsv(projectId, csvFile);
      setBulkResult(result);
      setMessage(
        `Bulk upload complete: ${formatNumber(result.inserted_count)} inserted, ${formatNumber(
          result.updated_count
        )} updated.`
      );
      await refreshDimensions(projectId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Bulk upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleEnrich() {
    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }

    const confirmed = window.confirm(
      "This will enrich normalized tickets with configured application dimensions. Raw uploaded data and raw ticket fields will not be changed."
    );
    if (!confirmed) {
      return;
    }

    setIsEnriching(true);
    setError(null);
    setMessage(null);
    try {
      const result = await enrichApplicationDimensions(projectId, replaceExisting);
      setSummary(result);
      setMessage(`Ticket enrichment complete: ${formatNumber(result.updated_tickets)} updated.`);
      await refreshDimensions(projectId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Ticket enrichment failed");
    } finally {
      setIsEnriching(false);
    }
  }

  async function handleDeactivate(dimension: ApplicationDimension) {
    const confirmed = window.confirm(
      `Deactivate mapping for ${dimension.application_name}? Existing enriched tickets are not deleted.`
    );
    if (!confirmed) {
      return;
    }

    setError(null);
    try {
      await deactivateApplicationDimension(dimension.id);
      setMessage("Application dimension deactivated.");
      await refreshDimensions(projectId);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to deactivate mapping"
      );
    }
  }

  return (
    <section className="upload-layout" aria-labelledby="application-dimensions-heading">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Configuration</p>
            <h2 id="application-dimensions-heading">Application Dimensions</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={!projectId.trim() || isLoadingDimensions}
              onClick={() => void refreshDimensions()}
            >
              {isLoadingDimensions ? "Refreshing..." : "Refresh"}
            </button>
            <button
              className="primary-button"
              type="button"
              disabled={!projectId.trim() || isEnriching}
              onClick={() => void handleEnrich()}
            >
              {isEnriching ? "Enriching..." : "Enrich Tickets"}
            </button>
          </div>
        </div>

        <div className="form-grid">
          <label>
            <span>Project ID</span>
            <input
              type="text"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              placeholder="Paste project UUID"
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={replaceExisting}
              onChange={(event) => setReplaceExisting(event.target.checked)}
            />
            <span>Replace existing ticket dimension assignments</span>
          </label>
        </div>

        <div className="message-stack" role="status" aria-live="polite">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
          <p className="muted-text">
            Enrichment updates only dimension assignment columns. Raw application, business
            service, CMDB CI, service offering, catalog item, and source data are preserved.
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Bulk Upload</p>
            <h2>Upload Mapping CSV</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            <span>Application dimension CSV</span>
            <input type="file" accept=".csv,text/csv" onChange={handleCsvSelection} />
          </label>
        </div>
        <div className="action-row">
          <button
            className="primary-button"
            type="button"
            disabled={!projectId.trim() || !csvFile || isUploading}
            onClick={() => void handleBulkUpload()}
          >
            {isUploading ? "Uploading..." : "Upload CSV"}
          </button>
        </div>
        {bulkResult ? (
          <div className="summary-grid mapping-summary-grid">
            <div>
              <p className="label">Rows</p>
              <strong>{formatNumber(bulkResult.total_rows)}</strong>
            </div>
            <div>
              <p className="label">Inserted</p>
              <strong>{formatNumber(bulkResult.inserted_count)}</strong>
            </div>
            <div>
              <p className="label">Updated</p>
              <strong>{formatNumber(bulkResult.updated_count)}</strong>
            </div>
            <div>
              <p className="label">Skipped</p>
              <strong>{formatNumber(bulkResult.skipped_count)}</strong>
            </div>
          </div>
        ) : null}
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">{editingId ? "Edit Mapping" : "Add Mapping"}</p>
            <h2>Dimension Mapping</h2>
          </div>
          <button className="secondary-button" type="button" onClick={clearForm}>
            Clear Form
          </button>
        </div>
        <form className="upload-form" onSubmit={(event) => void handleSave(event)}>
          <div className="form-grid">
            <label>
              <span>Customer Name</span>
              <input
                value={form.customer_name}
                onChange={(event) => updateFormField("customer_name", event.target.value)}
              />
            </label>
            <label>
              <span>Tower Name</span>
              <input
                value={form.tower_name}
                onChange={(event) => updateFormField("tower_name", event.target.value)}
              />
            </label>
            <label>
              <span>Cluster Name</span>
              <input
                value={form.cluster_name}
                onChange={(event) => updateFormField("cluster_name", event.target.value)}
              />
            </label>
            <label>
              <span>Application Group Name</span>
              <input
                value={form.application_group_name}
                onChange={(event) =>
                  updateFormField("application_group_name", event.target.value)
                }
              />
            </label>
            <label>
              <span>Application Name</span>
              <input
                value={form.application_name}
                onChange={(event) => updateFormField("application_name", event.target.value)}
              />
            </label>
            <label>
              <span>Application Alias</span>
              <input
                value={form.application_alias}
                onChange={(event) => updateFormField("application_alias", event.target.value)}
              />
            </label>
            <label>
              <span>Business Service Alias</span>
              <input
                value={form.business_service_alias}
                onChange={(event) =>
                  updateFormField("business_service_alias", event.target.value)
                }
              />
            </label>
            <label>
              <span>CMDB CI Alias</span>
              <input
                value={form.cmdb_ci_alias}
                onChange={(event) => updateFormField("cmdb_ci_alias", event.target.value)}
              />
            </label>
            <label>
              <span>Notes</span>
              <input
                value={form.notes}
                onChange={(event) => updateFormField("notes", event.target.value)}
              />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(event) => updateFormField("is_active", event.target.checked)}
              />
              <span>Active mapping</span>
            </label>
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              type="submit"
              disabled={!projectId.trim() || !form.application_name.trim() || isSaving}
            >
              {isSaving ? "Saving..." : editingId ? "Update Mapping" : "Create Mapping"}
            </button>
          </div>
        </form>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Configured Dimensions</p>
            <h2>{formatNumber(dimensions.length)} Mappings</h2>
          </div>
          <p className="muted-text">{formatNumber(activeCount)} active</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Application</th>
                <th>Aliases</th>
                <th>Hierarchy</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {dimensions.map((dimension) => (
                <tr key={dimension.id}>
                  <td>
                    <strong>{dimension.application_name}</strong>
                    <p className="muted-text">{dimension.notes}</p>
                  </td>
                  <td>
                    <p>App: {dimension.application_alias ?? "Not set"}</p>
                    <p>Service: {dimension.business_service_alias ?? "Not set"}</p>
                    <p>CI: {dimension.cmdb_ci_alias ?? "Not set"}</p>
                  </td>
                  <td>
                    <p>{dimension.customer_name ?? "No customer"}</p>
                    <p>{dimension.tower_name ?? "No tower"}</p>
                    <p>{dimension.cluster_name ?? "No cluster"}</p>
                    <p>{dimension.application_group_name ?? "No group"}</p>
                  </td>
                  <td>{dimension.is_active ? "Active" : "Inactive"}</td>
                  <td>
                    <div className="panel-actions">
                      <button
                        className="secondary-button table-action-button"
                        type="button"
                        onClick={() => {
                          setEditingId(dimension.id);
                          setForm(dimensionToForm(dimension));
                        }}
                      >
                        Edit
                      </button>
                      <button
                        className="secondary-button danger-button table-action-button"
                        type="button"
                        disabled={!dimension.is_active}
                        onClick={() => void handleDeactivate(dimension)}
                      >
                        Deactivate
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {dimensions.length === 0 ? (
                <tr>
                  <td colSpan={5}>No application dimensions loaded for this project.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {summary ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Enrichment Summary</p>
              <h2>Ticket Dimension Coverage</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">Total Tickets</p>
              <strong>{formatNumber(summary.total_tickets)}</strong>
            </div>
            <div>
              <p className="label">Matched</p>
              <strong>{formatNumber(summary.matched_tickets)}</strong>
            </div>
            <div>
              <p className="label">Unmatched</p>
              <strong>{formatNumber(summary.unmatched_tickets)}</strong>
            </div>
            <div>
              <p className="label">Match Rate</p>
              <strong>{formatNumber(summary.match_rate_pct, 1)}%</strong>
            </div>
          </div>
          <div className="summary-grid mapping-summary-grid">
            {Object.entries(summary.match_counts_by_source).map(([source, count]) => (
              <div key={source}>
                <p className="label">{source.replace(/_/g, " ")}</p>
                <strong>{formatNumber(count)}</strong>
              </div>
            ))}
          </div>
          <TopValues title="Top Unmatched Applications" values={summary.top_unmatched_applications} />
          <TopValues
            title="Top Unmatched Business Services"
            values={summary.top_unmatched_business_services}
          />
          <TopValues title="Top Unmatched CMDB CIs" values={summary.top_unmatched_cmdb_ci} />
          <TopValues
            title="Top Unmatched Service Offerings"
            values={summary.top_unmatched_service_offerings}
          />
          <TopValues title="Top Unmatched Catalog Items" values={summary.top_unmatched_catalog_items} />
        </div>
      ) : null}
    </section>
  );
}

export default ApplicationDimensions;
