import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  enrichApplicationInventory,
  getApplicationInventoryFilterValues,
  getApplicationInventorySummary,
  getUnmatchedBusinessServices,
  listApplicationInventory,
  uploadApplicationInventoryFile,
} from "./api/applicationInventory";
import type {
  ApplicationInventoryEnrichmentSummary,
  ApplicationInventoryFilterValues,
  ApplicationInventoryItem,
  ApplicationInventoryUploadResponse,
  UnmatchedBusinessServicesResponse,
  ValueCount,
} from "./api/applicationInventory";
import CustomerSelector from "./CustomerSelector";

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

function MessageList({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }

  return (
    <div className="summary-block">
      <p className="label">{title}</p>
      <ul className="selected-files">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
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

function FilterPreview({
  title,
  values,
}: {
  title: string;
  values: string[] | undefined;
}) {
  const previewValues = (values ?? []).slice(0, 12);
  return (
    <div className="summary-block">
      <p className="label">{title}</p>
      {previewValues.length === 0 ? (
        <p className="muted-text">No values yet.</p>
      ) : (
        <ul className="selected-files">
          {previewValues.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ApplicationInventory() {
  const [projectId, setProjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [inventoryItems, setInventoryItems] = useState<ApplicationInventoryItem[]>([]);
  const [uploadResult, setUploadResult] = useState<ApplicationInventoryUploadResponse | null>(null);
  const [summary, setSummary] = useState<ApplicationInventoryEnrichmentSummary | null>(null);
  const [coverage, setCoverage] = useState<UnmatchedBusinessServicesResponse | null>(null);
  const [filterValues, setFilterValues] = useState<ApplicationInventoryFilterValues | null>(null);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  async function refreshInventory(nextProjectId = projectId) {
    if (!nextProjectId.trim()) {
      setError("Select a customer first.");
      return;
    }

    setIsRefreshing(true);
    setError(null);
    try {
      const [items, nextSummary, nextCoverage, nextFilterValues] = await Promise.all([
        listApplicationInventory(nextProjectId),
        getApplicationInventorySummary(nextProjectId),
        getUnmatchedBusinessServices(nextProjectId, 50),
        getApplicationInventoryFilterValues(nextProjectId),
      ]);
      setInventoryItems(items);
      setSummary(nextSummary);
      setCoverage(nextCoverage);
      setFilterValues(nextFilterValues);
      setMessage("Application Inventory refreshed.");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to refresh inventory"
      );
    } finally {
      setIsRefreshing(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId.trim()) {
      setError("Select a customer first.");
      return;
    }
    if (!file) {
      setError("Select an Application Inventory CSV or XLSX file first.");
      return;
    }

    setIsUploading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await uploadApplicationInventoryFile(projectId, file);
      setUploadResult(result);
      setMessage(
        `Inventory upload complete: ${formatNumber(result.inserted_count)} inserted, ${formatNumber(
          result.updated_count
        )} updated.`
      );
      await refreshInventory(projectId);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Application Inventory upload failed"
      );
    } finally {
      setIsUploading(false);
    }
  }

  async function handleEnrich() {
    if (!projectId.trim()) {
      setError("Select a customer first.");
      return;
    }

    const confirmed = window.confirm(
      "This will enrich tickets from Application Inventory. Raw ticket fields and uploaded source data will not be changed."
    );
    if (!confirmed) {
      return;
    }

    setIsEnriching(true);
    setError(null);
    setMessage(null);
    try {
      const result = await enrichApplicationInventory(projectId, replaceExisting);
      setSummary(result);
      setMessage(`Enriched ${formatNumber(result.updated_tickets)} tickets.`);
      const [nextCoverage, nextFilterValues, nextItems] = await Promise.all([
        getUnmatchedBusinessServices(projectId, 50),
        getApplicationInventoryFilterValues(projectId),
        listApplicationInventory(projectId),
      ]);
      setCoverage(nextCoverage);
      setFilterValues(nextFilterValues);
      setInventoryItems(nextItems);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Application Inventory enrichment failed"
      );
    } finally {
      setIsEnriching(false);
    }
  }

  return (
    <section className="upload-layout" aria-labelledby="application-inventory-heading">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Application Inventory</p>
            <h2 id="application-inventory-heading">Application Inventory Upload</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => void refreshInventory()}
              disabled={!projectId.trim() || isRefreshing}
            >
              {isRefreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        <form className="upload-form" onSubmit={(event) => void handleUpload(event)}>
          <div className="form-grid">
            <CustomerSelector projectId={projectId} onProjectIdChange={setProjectId} />
            <label>
              <span>Inventory File</span>
              <input
                type="file"
                accept=".csv,.xlsx"
                onChange={handleFileSelection}
                disabled={isUploading}
              />
            </label>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              type="submit"
              disabled={isUploading || !projectId.trim() || !file}
            >
              {isUploading ? "Uploading..." : "Upload Application Inventory"}
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={handleEnrich}
              disabled={isEnriching || !projectId.trim()}
            >
              {isEnriching ? "Enriching..." : "Enrich Tickets"}
            </button>
          </div>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={replaceExisting}
              onChange={(event) => setReplaceExisting(event.target.checked)}
            />
            <span>Replace existing inventory enrichment</span>
          </label>
          <p className="scope-note">
            Enrichment updates only denormalized inventory fields. It does not change raw ticket
            fields or uploaded source data.
          </p>
        </form>

        <div className="message-stack">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </div>

      {uploadResult ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Upload Summary</p>
              <h2>Inventory File Results</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">Rows Processed</p>
              <strong>{formatNumber(uploadResult.total_rows)}</strong>
            </div>
            <div>
              <p className="label">Inserted</p>
              <strong>{formatNumber(uploadResult.inserted_count)}</strong>
            </div>
            <div>
              <p className="label">Updated</p>
              <strong>{formatNumber(uploadResult.updated_count)}</strong>
            </div>
            <div>
              <p className="label">Skipped</p>
              <strong>{formatNumber(uploadResult.skipped_count)}</strong>
            </div>
            <div>
              <p className="label">Business Services</p>
              <strong>{formatNumber(uploadResult.distinct_business_service_count)}</strong>
            </div>
            <div>
              <p className="label">Parent Applications</p>
              <strong>{formatNumber(uploadResult.distinct_parent_application_count)}</strong>
            </div>
            <div>
              <p className="label">Support Leads</p>
              <strong>{formatNumber(uploadResult.distinct_support_lead_count)}</strong>
            </div>
            <div>
              <p className="label">Functional Tracks</p>
              <strong>{formatNumber(uploadResult.distinct_functional_track_count)}</strong>
            </div>
            <div>
              <p className="label">AMS Owners</p>
              <strong>{formatNumber(uploadResult.distinct_ams_owner_count)}</strong>
            </div>
            <div>
              <p className="label">Vendors</p>
              <strong>{formatNumber(uploadResult.distinct_supported_vendor_count)}</strong>
            </div>
            <div>
              <p className="label">Application Owners</p>
              <strong>{formatNumber(uploadResult.distinct_application_owner_count)}</strong>
            </div>
            <div>
              <p className="label">Assignment Groups</p>
              <strong>{formatNumber(uploadResult.distinct_assignment_group_count)}</strong>
            </div>
          </div>
          <MessageList title="Warnings" values={uploadResult.warnings} />
          <MessageList title="Errors" values={uploadResult.errors} />
        </div>
      ) : null}

      {summary ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Enrichment Summary</p>
              <h2>Ticket Coverage</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">Total Tickets</p>
              <strong>{formatNumber(summary.total_tickets)}</strong>
            </div>
            <div>
              <p className="label">Matched Tickets</p>
              <strong>{formatNumber(summary.matched_tickets)}</strong>
            </div>
            <div>
              <p className="label">Unmatched Tickets</p>
              <strong>{formatNumber(summary.unmatched_tickets)}</strong>
            </div>
            <div>
              <p className="label">Match Rate</p>
              <strong>{formatPercent(summary.match_rate_pct)}</strong>
            </div>
            <div>
              <p className="label">Updated Tickets</p>
              <strong>{formatNumber(summary.updated_tickets)}</strong>
            </div>
            <div>
              <p className="label">Matched by Business Service</p>
              <strong>{formatNumber(summary.matched_by_business_service_count)}</strong>
            </div>
            <div>
              <p className="label">Matched by Application</p>
              <strong>{formatNumber(summary.matched_by_application_count)}</strong>
            </div>
            <div>
              <p className="label">Unmatched Business Services</p>
              <strong>{formatNumber(summary.unmatched_business_service_count)}</strong>
            </div>
          </div>
          <TopValues
            title="Top Unmatched Business Services"
            values={summary.top_unmatched_business_services}
          />
          <TopValues title="Top Unmatched Applications" values={summary.top_unmatched_applications} />
          <TopValues
            title="Top Unmatched Assignment Groups"
            values={summary.top_unmatched_assignment_groups}
          />
        </div>
      ) : null}

      {coverage ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Business Service Coverage</p>
              <h2>Ticket Business Services vs Inventory</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">Ticket Business Services</p>
              <strong>{formatNumber(coverage.distinct_ticket_business_service_count)}</strong>
            </div>
            <div>
              <p className="label">Inventory Business Services</p>
              <strong>{formatNumber(coverage.distinct_inventory_business_service_count)}</strong>
            </div>
            <div>
              <p className="label">Matched Business Services</p>
              <strong>{formatNumber(coverage.matched_business_service_count)}</strong>
            </div>
            <div>
              <p className="label">Coverage</p>
              <strong>{formatPercent(coverage.business_service_coverage_pct)}</strong>
            </div>
          </div>
          {coverage.rows.length === 0 ? (
            <p className="muted-text summary-block">No unmatched ticket business services found.</p>
          ) : (
            <div className="table-wrap summary-block">
              <table>
                <thead>
                  <tr>
                    <th>Business Service</th>
                    <th>Tickets</th>
                    <th>Assignment Groups</th>
                    <th>Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.rows.map((row) => (
                    <tr key={row.business_service}>
                      <td>{row.business_service}</td>
                      <td>{formatNumber(row.ticket_count)}</td>
                      <td>{formatNumber(row.assignment_group_count)}</td>
                      <td>
                        <span className="mono-text">
                          {row.sample_assignment_groups.join(", ") || "No groups"}
                        </span>
                        <br />
                        <span className="muted-text">
                          {row.sample_ticket_numbers.join(", ") || "No ticket samples"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Inventory Filter Preview</p>
            <h2>Future Dashboard Filters</h2>
          </div>
        </div>
        <div className="form-grid">
          <FilterPreview title="Functional Track" values={filterValues?.functional_tracks} />
          <FilterPreview title="AMS Owner" values={filterValues?.ams_owners} />
          <FilterPreview title="Supported By Vendor" values={filterValues?.supported_by_vendors} />
          <FilterPreview title="Support Lead (Managed By)" values={filterValues?.support_leads} />
          <FilterPreview title="Application Owner" values={filterValues?.application_owners} />
          <FilterPreview title="Parent Application" values={filterValues?.parent_application_names} />
          <FilterPreview
            title="Business Service CI Name"
            values={filterValues?.business_service_ci_names}
          />
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Configured Inventory</p>
            <h2>Uploaded Business Services</h2>
          </div>
        </div>
        {inventoryItems.length === 0 ? (
          <p className="muted-text">No inventory rows loaded yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Business Service CI Name</th>
                  <th>Parent Application</th>
                  <th>Assignment Group</th>
                  <th>Support Lead</th>
                  <th>Functional Track</th>
                  <th>AMS Owner</th>
                  <th>Vendor</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {inventoryItems.slice(0, 50).map((item) => (
                  <tr key={item.id}>
                    <td>{item.business_service_ci_name}</td>
                    <td>{item.parent_application_name ?? "Not set"}</td>
                    <td>{item.assignment_group ?? "Not set"}</td>
                    <td>{item.support_lead ?? "Not set"}</td>
                    <td>{item.functional_track ?? "Not set"}</td>
                    <td>{item.ams_owner ?? "Not set"}</td>
                    <td>{item.supported_by_vendor ?? "Not set"}</td>
                    <td>{item.active === false ? "No" : "Yes"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default ApplicationInventory;
