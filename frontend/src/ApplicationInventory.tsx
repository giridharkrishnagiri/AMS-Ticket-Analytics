import { useMemo, useState } from "react";
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
import type { ProjectOption } from "./api/projects";
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

function TopValues({
  title,
  values,
  countLabel = "Tickets",
}: {
  title: string;
  values: ValueCount[];
  countLabel?: string;
}) {
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
                <th>{countLabel}</th>
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

function topValueCounts<T>(
  items: T[],
  valueGetter: (item: T) => string | null | undefined,
  limit = 10
): ValueCount[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const value = valueGetter(item)?.trim();
    if (!value) {
      continue;
    }
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([value, count]) => ({ value, count }))
    .sort((left, right) => right.count - left.count || left.value.localeCompare(right.value))
    .slice(0, limit);
}

type ApplicationInventoryProps = {
  projectId?: string;
  selectedProject?: ProjectOption | null;
  onProjectIdChange?: (projectId: string) => void;
  onProjectChange?: (project: ProjectOption | null) => void;
  embedded?: boolean;
};

function ApplicationInventory({
  projectId: externalProjectId,
  selectedProject,
  onProjectIdChange,
  onProjectChange,
  embedded = false,
}: ApplicationInventoryProps = {}) {
  const [localProjectId, setLocalProjectId] = useState("");
  const projectId = externalProjectId ?? localProjectId;
  const setProjectId = onProjectIdChange ?? setLocalProjectId;
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

  const topFunctionalTracks = useMemo(
    () => topValueCounts(inventoryItems, (item) => item.functional_track),
    [inventoryItems]
  );
  const topAmsOwners = useMemo(
    () => topValueCounts(inventoryItems, (item) => item.ams_owner),
    [inventoryItems]
  );
  const topSupportedVendors = useMemo(
    () => topValueCounts(inventoryItems, (item) => item.supported_by_vendor),
    [inventoryItems]
  );
  const topHostingEnvs = useMemo(
    () => topValueCounts(inventoryItems, (item) => item.hosting_env),
    [inventoryItems]
  );
  const topSupportLeads = useMemo(
    () => topValueCounts(inventoryItems, (item) => item.support_lead),
    [inventoryItems]
  );
  const topApplicationOwners = useMemo(
    () => topValueCounts(inventoryItems, (item) => item.application_owner),
    [inventoryItems]
  );

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
            {embedded ? (
              <div className="info-card compact-info-card">
                <p className="label">Selected Customer</p>
                <strong>{selectedProject?.customer_name ?? "Select customer above"}</strong>
                <span>{selectedProject?.name ?? "Application Inventory uses the shared selector."}</span>
              </div>
            ) : (
              <CustomerSelector
                projectId={projectId}
                onProjectIdChange={setProjectId}
                onProjectChange={onProjectChange}
              />
            )}
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
              {isUploading ? "Uploading..." : "Upload CMDB/Application Inventory"}
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
            Application Inventory / CMDB upload is the source of truth for ticket scope
            classification. Tickets are in scope only when their Assignment Group matches a
            Support group marked In scope in the latest active CMDB file. Business Service CI Name
            is imported as an application attribute and is not used for ticket scope
            classification. Uploading a new file replaces the active inventory reference set for
            this project. Enrichment updates only denormalized inventory fields and does not
            change raw ticket fields or uploaded source data.
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
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Inventory Summary</p>
            <h2>Top Application Inventory Values</h2>
          </div>
        </div>
        <div className="summary-grid">
          <div>
            <p className="label">Inventory Rows</p>
            <strong>{formatNumber(inventoryItems.length)}</strong>
          </div>
          <div>
            <p className="label">Functional Tracks</p>
            <strong>{formatNumber(filterValues?.functional_tracks.length ?? 0)}</strong>
          </div>
          <div>
            <p className="label">AMS Owners</p>
            <strong>{formatNumber(filterValues?.ams_owners.length ?? 0)}</strong>
          </div>
          <div>
            <p className="label">Supported Vendors</p>
            <strong>{formatNumber(filterValues?.supported_by_vendors.length ?? 0)}</strong>
          </div>
          <div>
            <p className="label">Hosting Env</p>
            <strong>{formatNumber(filterValues?.hosting_envs.length ?? 0)}</strong>
          </div>
        </div>
        <div className="top-list-grid">
          <TopValues title="Top 10 Functional Tracks" values={topFunctionalTracks} countLabel="Rows" />
          <TopValues title="Top 10 AMS Owners" values={topAmsOwners} countLabel="Rows" />
          <TopValues title="Top 10 Supported Vendors" values={topSupportedVendors} countLabel="Rows" />
          <TopValues title="Top 10 Hosting Env" values={topHostingEnvs} countLabel="Rows" />
          <TopValues title="Top 10 Support Leads" values={topSupportLeads} countLabel="Rows" />
          <TopValues
            title="Top 10 Application Owners"
            values={topApplicationOwners}
            countLabel="Rows"
          />
        </div>
      </div>
    </section>
  );
}

export default ApplicationInventory;
